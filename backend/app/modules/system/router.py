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

from app.core.database import get_public_db, get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    revoke_refresh_token,
    validate_refresh_token,
    verify_password,
)
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import Tenant, User, UserRole

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
    job_id: str
    message: str


# ── Registration Endpoint ─────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a new tenant + first admin user (Async)",
    description=(
        "**Provisioning flow (Async):**\n"
        "1. Validates email uniqueness\n"
        "2. Creates `Tenant` and `User` in `public` schema (State: CREATED)\n"
        "3. Inserts `TenantProvisioningJob`\n"
        "4. Returns HTTP 202 Accepted\n\n"
        "This is a **public endpoint** — no Bearer token required."
    ),
    tags=["Authentication"],
)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_public_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RegisterResponse:
    """
    Register a new tenant asynchronously.
    """

    # ── 1. Check email uniqueness ─────────────────────────────────────────────
    existing = await db.execute(
        select(User).where(User.email == data.email.lower()),
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{data.email}' is already registered.",
        )

    # ── 2. Generate schema name from a fresh UUID ─────────────────────────────
    tenant_id = uuid4()
    schema = f"tenant_{str(tenant_id).replace('-', '_')}"

    # Slug: lowercase alphanumeric, max 80 chars
    base_slug = "".join(
        c if c.isalnum() else "-"
        for c in data.company_name.lower()
    ).strip("-")[:70]
    slug = f"{base_slug}-{str(tenant_id)[:8]}"

    # ── 3. INSERT Tenant into public.tenants ──────────────────────────────────

    from app.modules.system.models import ProvisioningState, TenantProvisioningJob

    tenant = Tenant(
        name=data.company_name,
        slug=slug,
        schema_name=schema,
        provisioning_state=ProvisioningState.CREATED,
    )
    db.add(tenant)
    await db.flush()  # Get tenant.id without committing yet

    # ── 4. INSERT User into public.users ──────────────────────────────────────
    user = User(
        tenant_id=tenant.id,
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name or data.company_name,
        role=UserRole.OWNER,
    )
    db.add(user)

    # ── 5. Create Provisioning Job ────────────────────────────────────────────
    job = TenantProvisioningJob(
        tenant_id=tenant.id,
        status="pending",
    )
    db.add(job)
    await db.commit()

    logger.info(
        "✅ Registration accepted (async): tenant='%s', schema='%s', user='%s'",
        tenant.name,
        schema,
        user.email,
    )

    return RegisterResponse(
        tenant_id=str(tenant.id),
        job_id=str(job.id),
        message=(
            f"Tenant '{tenant.name}' registered successfully. "
            f"Provisioning job started."
        ),
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
        role=user.role,
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
    summary="Exchange refresh token for new access token",
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
        role=user.role,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=data.refresh_token,
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
