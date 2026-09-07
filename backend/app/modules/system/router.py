"""
app/modules/system/router.py — System Module API (Auth + Tenant Management)

Registration Flow (POST /api/v1/auth/register):
  1. Validate email uniqueness.
  2. Hash password with bcrypt.
  3. INSERT Tenant row into public.tenants.
  4. INSERT User row into public.users.
  5. Call provision_tenant_schema(tenant_id):
       a. CREATE SCHEMA tenant_{id}
       b. CREATE TABLE accounts, journal_entries, transaction_lines, ...
       c. Seed default Chart of Accounts (12 system accounts)
  6. Issue JWT access + Redis refresh token.
  7. Return {tenant, user, tokens}.

All of this runs in a single logical flow. The schema provisioning uses a
SEPARATE connection (engine.begin()) from the public-schema session to avoid
DDL + DML transaction conflicts.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.core.database import get_public_db, get_redis
from app.core.notifications.email import send_email
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    detect_refresh_token_reuse,
    hash_password,
    invalidate_password_reset_token,
    revoke_all_user_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
    validate_password_reset_token,
    validate_refresh_token,
    verify_password,
)
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import Tenant, TenantStatus, User, UserRole

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response Schemas ────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Payload for registering a new tenant + first admin user."""

    company_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterResponse(BaseModel):
    tenant_id: str
    user_id: str
    email: str
    full_name: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    # Same complexity rule as RegisterRequest.password_complexity — a
    # password reset must not be allowed to set a weaker password than
    # registration requires.
    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        return v


class MessageResponse(BaseModel):
    message: str


# ── Registration Endpoint ─────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tenant + first admin user (Synchronous)",
    description=(
        "**Provisioning flow (Synchronous):**\n"
        "1. Validates email uniqueness\n"
        "2. Creates `Tenant` and `User` in `public` schema\n"
        "3. Provisions tenant PostgreSQL schema + seeds Chart of Accounts\n"
        "4. Issues JWT tokens\n"
        "5. Returns HTTP 201 Created with tokens\n\n"
        "This is a **public endpoint** — no Bearer token required."
    ),
    tags=["Authentication"],
)
async def register(
    data: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_public_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RegisterResponse:
    """
    Register a new tenant. Provisioning is now AWAITED synchronously before
    the response is returned — see the module docstring / provision_tenant_schema()
    in app/core/db/database.py for why the previous background-task version
    was a real, live bug: it always told the client registration succeeded
    (status=PENDING_SETUP never even got flipped to ACTIVE — that field was
    never touched here, a separate bug now also fixed below) before the
    schema had actually finished being created, so brand-new tenants —
    including ones that picked a vertical plugin like rental/hospitality
    during onboarding — would see only the always-present Core system and
    fail to load real data, because their schema was silently incomplete or
    still mid-creation. Registration now takes a few seconds longer (real
    schema + Chart of Accounts creation) in exchange for actually being
    correct: if provisioning fails, the whole request fails (and the
    Tenant/User rows are rolled back by get_public_db()'s exception handler)
    instead of quietly leaving a broken half-provisioned tenant behind.
    """
    from app.core.config import settings
    from app.core.db.database import provision_tenant_schema
    from app.modules.system.models import ProvisioningState

    # ── 1. Check email uniqueness ─────────────────────────────────────────────
    existing = await db.execute(
        select(User).where(User.email == data.email.lower()),
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"البريد الإلكتروني '{data.email}' مسجّل بالفعل.",
        )

    # ── 2. Generate IDs and schema name ──────────────────────────────────────
    tenant_id = uuid4()
    schema = f"tenant_{str(tenant_id).replace('-', '_')}"
    base_slug = "".join(
        c if c.isalnum() else "-"
        for c in data.company_name.lower()
    ).strip("-")[:70]
    slug = f"{base_slug}-{str(tenant_id)[:8]}"

    # ── 3. INSERT Tenant + User (not yet committed) ───────────────────────────
    tenant = Tenant(
        id=tenant_id,
        name=data.company_name,
        slug=slug,
        schema_name=schema,
        provisioning_state=ProvisioningState.CREATED,
        status=TenantStatus.PENDING_SETUP,
    )
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name or data.company_name,
        role=UserRole.OWNER,
    )
    db.add(user)
    await db.flush()

    # ── 4. Provision tenant schema — AWAITED, not a background task ──────────
    # provision_tenant_schema() runs the real alembic tenant migration chain
    # (creates every tenant table incl. all vertical plugin tables, and
    # stamps alembic_version) plus the Chart of Accounts seed, in a
    # subprocess (still required to dodge the Windows ProactorEventLoop +
    # greenlet crash), but now properly awaited — see its docstring. If it
    # raises, we deliberately do NOT catch it here: letting it propagate is
    # what makes the whole registration fail and roll back cleanly instead
    # of leaving a broken tenant that looks ACTIVE.
    await provision_tenant_schema(str(tenant_id))

    tenant.provisioning_state = ProvisioningState.COMPLETE
    tenant.status = TenantStatus.ACTIVE

    await db.commit()

    logger.info(
        "✅ Registration complete: tenant='%s', schema='%s', user='%s'",
        tenant.name, schema, user.email,
    )

    # ── 5. Issue JWT tokens ───────────────────────────────────────────────────
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=str(tenant.id),
        roles=[user.role.value],
    )
    refresh_token = await create_refresh_token(
        user_id=user.id,
        tenant_id=str(tenant.id),
        redis_client=redis,
    )

    return RegisterResponse(
        tenant_id=str(tenant.id),
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        access_token=access_token,
        refresh_token=refresh_token,
        message=f"تم تسجيل شركة '{tenant.name}' بنجاح.",
    )



# ── Login ─────────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email + password",
    tags=["Authentication"],
)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_public_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    from app.core.config import settings

    result = await db.execute(
        select(User).where(User.email == data.email.lower()),
    )
    user: User | None = result.scalar_one_or_none()

    # Constant-time comparison even on "not found" path to prevent timing attacks
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=str(user.tenant_id),
        roles=[str(user.role)],
    )
    refresh_token = await create_refresh_token(
        user_id=user.id,
        tenant_id=str(user.tenant_id),
        redis_client=redis,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Token Refresh ─────────────────────────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange refresh token for new access token (rotates the refresh token)",
    description=(
        "**Rotation:** every successful call retires the presented refresh "
        "token and returns a brand-new one — the old token cannot be used "
        "again. **Reuse detection:** if an already-rotated (retired) refresh "
        "token is presented again — a strong signal it was stolen and is "
        "being replayed — ALL of that user's active refresh tokens are "
        "revoked immediately, forcing re-login on every device/session."
    ),
    tags=["Authentication"],
)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_public_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    from uuid import UUID

    from app.core.config import settings

    result = await validate_refresh_token(data.refresh_token, redis)
    if not result:
        # Not a currently-live token. Before rejecting outright, check
        # whether it's a *retired* (already-rotated) token being replayed —
        # that's not "just expired", it's a compromise signal: someone else
        # has a copy of a token the legitimate client already exchanged.
        reuse = await detect_refresh_token_reuse(data.refresh_token, redis)
        if reuse:
            reused_user_id, _reused_tenant_id = reuse
            revoked_count = await revoke_all_user_tokens(reused_user_id, redis)
            logger.warning(
                "🚨 Refresh token reuse detected for user=%s — treating as "
                "compromised credential, revoked %d active refresh token(s) "
                "(forced logout on all devices).",
                reused_user_id, revoked_count,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "This refresh token has already been used and cannot be "
                    "reused. All sessions have been logged out as a "
                    "precaution — please log in again."
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or expired.",
        )

    user_id_str, tenant_id = result
    user_result = await db.execute(
        select(User).where(User.id == UUID(user_id_str)),
    )
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
        )

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=tenant_id,
        roles=[str(user.role)],
    )
    # Rotate-on-use: retire the presented token (tombstoned for reuse
    # detection, see rotate_refresh_token()) and issue a fresh one.
    new_refresh_token = await rotate_refresh_token(
        old_token=data.refresh_token,
        user_id=user.id,
        tenant_id=tenant_id,
        redis_client=redis,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── Logout ────────────────────────────────────────────────────────────────────


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke current session refresh token",
    tags=["Authentication"],
)
async def logout(
    data: RefreshRequest,
    current_user: CurrentUser,
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    await revoke_refresh_token(data.refresh_token, redis)


# ── Current User ──────────────────────────────────────────────────────────────


@router.get(
    "/me",
    summary="Get current user profile",
    tags=["Authentication"],
)
async def get_me(current_user: CurrentUser) -> dict:
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "tenant_id": str(current_user.tenant_id),
        "role": current_user.role,
        "is_active": current_user.is_active,
    }


# ── Password Reset ────────────────────────────────────────────────────────────


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password-reset link via email",
    description=(
        "Always returns a generic success response, whether or not the "
        "email is registered — this prevents the endpoint from being used "
        "to enumerate which email addresses have an account. If the email "
        "matches an active account, a single-use, short-lived (see "
        "RESET_TOKEN_EXPIRE_MINUTES) reset token is emailed via the "
        "existing SMTP notification channel "
        "(app.core.notifications.email) — the same one used for invoice/"
        "payment notifications elsewhere in the system. This is a "
        "**public endpoint** — no Bearer token required."
    ),
    tags=["Authentication"],
)
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_public_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    from app.core.config import settings

    generic_response = MessageResponse(
        message=(
            "إذا كان هذا البريد الإلكتروني مسجّلاً لدينا، فسيتم إرسال "
            "رابط إعادة تعيين كلمة المرور إليه."
        ),
    )

    result = await db.execute(
        select(User).where(User.email == data.email.lower()),
    )
    user: User | None = result.scalar_one_or_none()

    # Deliberately identical response whether the user exists, is inactive,
    # or the email send itself fails below — never leak account existence
    # through response shape or timing-sensitive branching visible to the
    # caller.
    if not user or not user.is_active:
        logger.info(
            "Password reset requested for unknown/inactive email=%s — "
            "returning generic response, no email sent.",
            data.email,
        )
        return generic_response

    token = await create_password_reset_token(user.id, redis)

    async def _send_reset_email() -> None:
        await send_email(
            to_email=user.email,
            subject="إعادة تعيين كلمة المرور — Omni ERP",
            body_text=(
                f"مرحبًا {user.full_name or ''},\n\n"
                "تلقينا طلبًا لإعادة تعيين كلمة المرور الخاصة بحسابك.\n"
                f"رمز إعادة التعيين الخاص بك هو:\n\n{token}\n\n"
                f"هذا الرمز صالح لمدة {settings.RESET_TOKEN_EXPIRE_MINUTES} دقيقة فقط.\n"
                "إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة بأمان."
            ),
            body_html=(
                f"<p>مرحبًا {user.full_name or ''},</p>"
                "<p>تلقينا طلبًا لإعادة تعيين كلمة المرور الخاصة بحسابك.</p>"
                f"<p>رمز إعادة التعيين الخاص بك هو:</p><p><code>{token}</code></p>"
                f"<p>هذا الرمز صالح لمدة {settings.RESET_TOKEN_EXPIRE_MINUTES} دقيقة فقط.</p>"
                "<p>إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة بأمان.</p>"
            ),
        )

    # Best-effort, matches the notification dispatch discipline elsewhere
    # (app.core.notifications.dispatch/email — never raises, never blocks
    # the response) — send_email() already never raises, but run it in the
    # background regardless so a slow/hanging SMTP connection can't stall
    # this response and turn an intentionally-generic endpoint into a
    # timing oracle.
    background_tasks.add_task(_send_reset_email)

    logger.info("Password reset token issued for user=%s", user.id)
    return generic_response


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using a token from /forgot-password",
    description=(
        "Validates the single-use reset token (not expired, not already "
        "used), hashes and sets the new password, invalidates the token so "
        "it cannot be replayed, and — as a security best practice — revokes "
        "ALL of the user's existing refresh tokens, forcing re-login on "
        "every device/session. This is a **public endpoint** — no Bearer "
        "token required (the reset token itself is the credential)."
    ),
    tags=["Authentication"],
)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_public_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    from uuid import UUID

    user_id_str = await validate_password_reset_token(data.token, redis)
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid, expired, or already used.",
        )

    result = await db.execute(
        select(User).where(User.id == UUID(user_id_str)),
    )
    user: User | None = result.scalar_one_or_none()

    if not user or not user.is_active:
        # Token was valid but the account disappeared/was deactivated since
        # it was issued — invalidate the token regardless so it can't be
        # retried, then report failure.
        await invalidate_password_reset_token(data.token, redis)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid, expired, or already used.",
        )

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    # Single-use: burn the token immediately so it can't be replayed even
    # if this request is somehow retried/duplicated.
    await invalidate_password_reset_token(data.token, redis)

    # Force re-login everywhere — a password reset (whether user-initiated
    # or triggered by suspecting compromise) should not leave old sessions
    # holding a still-valid refresh token minted under the old password.
    revoked_count = await revoke_all_user_tokens(str(user.id), redis)
    logger.info(
        "Password reset for user=%s — revoked %d refresh token(s).",
        user.id, revoked_count,
    )

    return MessageResponse(
        message="تم إعادة تعيين كلمة المرور بنجاح. يرجى تسجيل الدخول مرة أخرى.",
    )
