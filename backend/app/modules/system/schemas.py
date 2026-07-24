"""
app/modules/system/schemas.py — Request/Response Pydantic Models (System Module)

These schemas are separate from the SQLModel ORM models to enforce
a clean API contract. They control exactly what data is accepted
in requests and what is returned in responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.system.models import PlanTier, TenantStatus


# ── Tenant Registration ───────────────────────────────────────────────────────


class TenantRegisterRequest(BaseModel):
    """Payload for registering a new tenant + creating the first admin user."""

    # Tenant info
    company_name: str = Field(min_length=2, max_length=255, examples=["مؤسسة الفلاح للتجارة"])
    business_type: str | None = Field(default=None, max_length=100, examples=["wholesale"])
    country_code: str = Field(default="EG", max_length=2)
    currency_code: str = Field(default="EGP", max_length=3)
    timezone: str = Field(default="Africa/Cairo", max_length=50)

    # First admin user
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)
    admin_full_name: str = Field(min_length=2, max_length=255)

    @field_validator("admin_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        return v


class TenantResponse(BaseModel):
    """Public tenant information returned after registration or lookup."""

    id: UUID
    name: str
    slug: str
    schema_name: str
    status: TenantStatus
    plan: PlanTier
    country_code: str
    currency_code: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Authentication ────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """Standard email + password login."""

    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """JWT tokens returned after successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class RefreshTokenRequest(BaseModel):
    """Request a new access token using a refresh token."""

    refresh_token: str


# ── User ──────────────────────────────────────────────────────────────────────


class UserCreateRequest(BaseModel):
    """Create a new user within the current tenant."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    roles: list[str] = Field(default_factory=lambda: ["staff"])


class UserUpdateRequest(BaseModel):
    """Partial update of a user's profile."""

    full_name: str | None = Field(default=None, max_length=255)
    roles: list[str] | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """Public user information (never exposes hashed_password)."""

    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    roles: list[str]
    is_active: bool
    is_superadmin: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


# ── Subscription ──────────────────────────────────────────────────────────────


class SubscriptionResponse(BaseModel):
    """Tenant's active subscription details."""

    id: UUID
    tenant_id: UUID
    plan_name: PlanTier
    started_at: datetime
    expires_at: datetime | None
    features: dict[str, Any]

    model_config = {"from_attributes": True}


# ── Shared ────────────────────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    """Generic success message wrapper."""

    message: str
    detail: dict[str, Any] | None = None
