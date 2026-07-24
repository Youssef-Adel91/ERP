"""
app/modules/system/service.py — System Business Logic

Handles tenant registration, user management, and authentication.
All operations on global tables go through this service layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.core.database import create_tenant_schema
from app.core.event_bus import TenantProvisionedEvent, get_event_bus
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    validate_refresh_token,
    verify_password,
)
from app.modules.system.models import (
    PlanTier,
    Subscription,
    Tenant,
    TenantStatus,
    User,
)
from app.modules.system.schemas import (
    TenantRegisterRequest,
    TokenResponse,
    UserCreateRequest,
)

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when credentials are invalid or the account is inactive."""


class TenantNotFoundError(Exception):
    """Raised when a requested tenant does not exist."""


class UserNotFoundError(Exception):
    """Raised when a requested user does not exist."""


class DuplicateEmailError(Exception):
    """Raised when attempting to register an already-used email."""


# ── Tenant Service ────────────────────────────────────────────────────────────


async def register_tenant(
    data: TenantRegisterRequest,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> tuple[Tenant, User, TokenResponse]:
    """
    Register a new tenant, provision their schema, and create the first admin.

    Workflow:
      1. Validate email uniqueness.
      2. Create Tenant record in public.tenants.
      3. Create default Subscription for the tenant.
      4. Create the first admin User.
      5. Provision the tenant's PostgreSQL schema (CREATE SCHEMA).
      6. Emit TenantProvisionedEvent so other modules can initialize.
      7. Issue JWT tokens for the new admin.

    Returns:
        Tuple of (Tenant, User, TokenResponse).
    """
    # 1. Check email uniqueness
    existing_user = await db.execute(
        select(User).where(User.email == data.admin_email)
    )
    if existing_user.scalar_one_or_none():
        raise DuplicateEmailError(f"Email '{data.admin_email}' is already registered.")

    # 2. Create Tenant
    from python_slugify import slugify  # type: ignore[import-untyped]

    base_slug = slugify(data.company_name, max_length=80, word_boundary=True)
    # Ensure slug uniqueness by appending a short UUID fragment
    from uuid import uuid4
    unique_suffix = str(uuid4())[:8]
    slug = f"{base_slug}-{unique_suffix}"
    tenant_id = uuid4()
    schema_name = f"tenant_{str(tenant_id).replace('-', '_')}"

    tenant = Tenant(
        id=tenant_id,
        name=data.company_name,
        slug=slug,
        schema_name=schema_name,
        business_type=data.business_type,
        country_code=data.country_code,
        currency_code=data.currency_code,
        timezone=data.timezone,
        status=TenantStatus.PENDING_SETUP,
        plan=PlanTier.FREE,
    )
    db.add(tenant)

    # 3. Create default Subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        plan_name=PlanTier.FREE,
    )
    db.add(subscription)

    # 4. Create first admin User
    user_id = uuid4()
    admin_user = User(
        id=user_id,
        tenant_id=tenant.id,
        email=data.admin_email,
        hashed_password=hash_password(data.admin_password),
        full_name=data.admin_full_name,
        roles=["admin"],
    )
    db.add(admin_user)

    await db.flush()  # Flush to DB to get IDs, but don't commit yet

    # 5. Provision PostgreSQL schema (outside the session transaction)
    await create_tenant_schema(str(tenant_id))

    # 6. Update tenant status to active
    tenant.status = TenantStatus.ACTIVE
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(admin_user)

    # 7. Emit system-level event
    event_bus = get_event_bus()
    await event_bus.publish(
        TenantProvisionedEvent(
            tenant_id="system",
            payload={
                "tenant_id": str(tenant.id),
                "schema_name": schema_name,
                "admin_user_id": str(admin_user.id),
            },
        )
    )

    # 8. Issue JWT tokens
    access_token = create_access_token(
        user_id=admin_user.id,
        tenant_id=str(tenant.id),
        roles=admin_user.roles,
    )
    refresh_token = await create_refresh_token(
        user_id=admin_user.id,
        tenant_id=str(tenant.id),
        redis_client=redis,
    )

    from app.core.config import settings

    token_response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    logger.info(
        "Tenant '%s' registered successfully (schema: %s)", tenant.name, schema_name
    )
    return tenant, admin_user, token_response


async def get_tenant_by_id(tenant_id: UUID, db: AsyncSession) -> Tenant:
    """Fetch a tenant by UUID. Raises TenantNotFoundError if not found."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise TenantNotFoundError(f"Tenant '{tenant_id}' not found.")
    return tenant


# ── Authentication Service ────────────────────────────────────────────────────


async def login(
    email: str,
    password: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> TokenResponse:
    """
    Authenticate a user with email + password.

    Returns JWT access + refresh tokens on success.
    Raises AuthenticationError on invalid credentials or inactive account.
    """
    # Lookup user by email
    result = await db.execute(select(User).where(User.email == email))
    user: User | None = result.scalar_one_or_none()

    # Use constant-time comparison to prevent timing attacks
    if not user or not verify_password(password, user.hashed_password):
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated. Contact your administrator.")

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    # Issue tokens
    from app.core.config import settings

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=str(user.tenant_id),
        roles=user.roles,
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


async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access token.

    The refresh token is NOT rotated to avoid race conditions in mobile apps.
    Its TTL is reset on each use.
    """
    from app.core.config import settings

    result = await validate_refresh_token(refresh_token, redis)
    if not result:
        raise AuthenticationError("Refresh token is invalid or expired.")

    user_id_str, tenant_id = result

    # Re-fetch user to get current roles (may have changed since last login)
    db_result = await db.execute(
        select(User).where(User.id == UUID(user_id_str))
    )
    user: User | None = db_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthenticationError("User account not found or deactivated.")

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=tenant_id,
        roles=user.roles,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,  # Same refresh token returned
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── User Management Service ───────────────────────────────────────────────────


async def create_user(
    data: UserCreateRequest,
    tenant_id: UUID,
    db: AsyncSession,
) -> User:
    """Create a new user within the current tenant."""
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise DuplicateEmailError(f"Email '{data.email}' is already in use.")

    user = User(
        tenant_id=tenant_id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        roles=data.roles,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(user_id: UUID, db: AsyncSession) -> User:
    """Fetch a user by UUID. Raises UserNotFoundError if not found."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UserNotFoundError(f"User '{user_id}' not found.")
    return user
