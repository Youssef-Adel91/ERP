"""
app/modules/system/models.py — Public Schema ORM Models

ALL tables here use `{"schema": "public"}` so SQLAlchemy always
targets the global public schema, regardless of the session's search_path.
This is intentional: Tenant and User are global entities, not per-tenant.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, String, UniqueConstraint, text, Column
import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel


# ── Enumerations ──────────────────────────────────────────────────────────────


class PlanTier(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    PENDING_SETUP = "pending_setup"
    SUSPENDED = "suspended"


# ── Tenant ────────────────────────────────────────────────────────────────────


class Tenant(SQLModel, table=True):
    """
    One row per registered merchant/company.
    The `schema_name` column is the PostgreSQL schema that isolates their data.
    """

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        UniqueConstraint("schema_name", name="uq_tenants_schema_name"),
        {"schema": "public"},
    )

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    name: str = Field(max_length=255, index=True)
    slug: str = Field(max_length=120, index=True)

    # The PostgreSQL schema name for this tenant: "tenant_<uuid_no_dashes>"
    schema_name: str = Field(max_length=80)

    # Business profile
    country_code: str = Field(default="EG", max_length=2)
    currency_code: str = Field(default="EGP", max_length=3)
    timezone: str = Field(default="Africa/Cairo", max_length=50)

    status: TenantStatus = Field(default=TenantStatus.PENDING_SETUP)
    plan: PlanTier = Field(default=PlanTier.FREE)
    active_plugins: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list, nullable=False))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc).replace(tzinfo=None)},
    )

    # Relationships — back-populated from User
    users: list["User"] = Relationship(back_populates="tenant")


# ── User ──────────────────────────────────────────────────────────────────────



class UserRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    SALES = "SALES"
    ACCOUNTING = "ACCOUNTING"

class User(SQLModel, table=True):
    """
    A platform user. Stored in `public` schema so login (email lookup)
    works without knowing the tenant first.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        {"schema": "public"},
    )

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )

    # FK into public.tenants
    tenant_id: UUID = Field(foreign_key="public.tenants.id", index=True)

    email: str = Field(max_length=320, index=True)
    hashed_password: str = Field(max_length=255)
    full_name: str = Field(max_length=255, default="")

    # JSON list of role strings: ["admin", "accountant", "sales"]
    role: UserRole = Field(default=UserRole.OWNER, sa_column=Column(sa.Enum(UserRole, name='userrole'), default=UserRole.OWNER, nullable=False))

    is_active: bool = Field(default=True)
    is_superadmin: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )
    last_login_at: datetime | None = Field(default=None)

    # Relationships
    tenant: Tenant = Relationship(back_populates="users")
