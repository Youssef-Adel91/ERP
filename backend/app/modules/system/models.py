"""
app/modules/system/models.py — System ORM Models (Public & Tenant Schemas)

Contains global identities (Tenant, User) in the `public` schema.
Contains `TenantUser` (RBAC) in the `tenant` schema.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, Index, UniqueConstraint, func, text
from sqlmodel import Field, Relationship

from app.core.db.base import PublicBase, TenantBase

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
    READ_ONLY = "read_only"

class ProvisioningState(StrEnum):
    CREATED = "created"
    SCHEMA_CREATED = "schema_created"
    TABLES_CREATED = "tables_created"
    COA_SEEDED = "coa_seeded"
    BRANCH_CREATED = "branch_created"
    TREASURY_CREATED = "treasury_created"
    WAREHOUSE_CREATED = "warehouse_created"
    SEQUENCES_CREATED = "sequences_created"
    PERIODS_CREATED = "periods_created"
    COMPLETE = "complete"
    FAILED = "failed"

class UserRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    SALES = "SALES"
    ACCOUNTING = "ACCOUNTING"


# ── Public Schema Models ──────────────────────────────────────────────────────

class Tenant(PublicBase, table=True):
    """
    One row per registered merchant/company.
    """
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        UniqueConstraint("schema_name", name="uq_tenants_schema_name"),
        {"schema": "public"},
    )

    name: str = Field(max_length=255, index=True)
    slug: str = Field(max_length=120, index=True)
    schema_name: str = Field(max_length=80)
    
    # New V2 Fields
    shard_id: str | None = Field(default=None, max_length=50)
    db_cluster_ref: str | None = Field(default=None, max_length=100)
    schema_version: str | None = Field(default=None, max_length=50)
    plan: PlanTier = Field(default=PlanTier.FREE)
    provisioning_state: ProvisioningState = Field(default=ProvisioningState.CREATED)
    trust_consent: bool = Field(default=False)

    country_code: str = Field(default="EG", max_length=2)
    currency_code: str = Field(default="EGP", max_length=3)
    timezone: str = Field(default="Africa/Cairo", max_length=50)
    status: TenantStatus = Field(default=TenantStatus.PENDING_SETUP)
    active_plugins: list[str] = Field(default_factory=list, sa_column=Column(JSON, default=list, nullable=False))

    # Relationships
    users: list["User"] = Relationship(back_populates="tenant")


class User(PublicBase, table=True):
    """
    Global platform user. Used for cross-tenant login.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        {"schema": "public"},
    )

    tenant_id: UUID = Field(foreign_key="public.tenants.id", index=True)
    email: str = Field(max_length=320, index=True)
    hashed_password: str = Field(max_length=255)
    full_name: str = Field(max_length=255, default="")
    
    # Global fallback role, but real RBAC happens via TenantUser
    role: UserRole = Field(default=UserRole.OWNER, sa_column=Column(sa.Enum(UserRole, name='userrole'), default=UserRole.OWNER, nullable=False))
    is_active: bool = Field(default=True)
    is_superadmin: bool = Field(default=False)
    last_login_at: datetime | None = Field(default=None)

    # Relationships
    tenant: Tenant = Relationship(back_populates="users")


class TenantProvisioningJob(PublicBase, table=True):
    __tablename__ = "tenant_provisioning_jobs"
    __table_args__ = ({"schema": "public"},)

    tenant_id: UUID = Field(foreign_key="public.tenants.id", index=True)
    status: str = Field(default="pending", max_length=50)
    error_message: str | None = Field(default=None)


class TenantMigration(PublicBase, table=True):
    __tablename__ = "tenant_migrations"
    __table_args__ = ({"schema": "public"},)
    tenant_id: UUID = Field(foreign_key="public.tenants.id", index=True)
    target_version: str = Field(max_length=50)


class Plugin(PublicBase, table=True):
    __tablename__ = "plugins"
    __table_args__ = ({"schema": "public"},)
    name: str = Field(max_length=100, index=True)


class TenantPlugin(PublicBase, table=True):
    __tablename__ = "tenant_plugins"
    __table_args__ = ({"schema": "public"},)
    tenant_id: UUID = Field(foreign_key="public.tenants.id", index=True)
    plugin_id: UUID = Field(foreign_key="public.plugins.id", index=True)




class OutboxEvent(PublicBase, table=True):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        {"schema": "public"},
    )
    
    tenant_id: UUID = Field(index=True)
    aggregate_type: str = Field(max_length=50)
    aggregate_id: UUID = Field(index=True)
    event_type: str = Field(max_length=100)
    event_version: int = Field(default=1)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    
    occurred_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    published_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    attempts: int = Field(default=0)
    last_error: str | None = Field(default=None)


class PlatformAuditLog(PublicBase, table=True):
    __tablename__ = "platform_audit_logs"
    __table_args__ = ({"schema": "public"},)
    action: str = Field(max_length=100)


# ── Tenant Schema Models ──────────────────────────────────────────────────────

class TenantUser(TenantBase, table=True):
    """
    Tenant-specific user record. Holds RBAC and branch assignments.
    Targets for `created_by` / `updated_by` ForeignKeys across tenant schemas.
    """
    __tablename__ = "tenant_users"
    __table_args__ = ({"schema": "tenant"},)
    
    # We reference the public User via UUID, but SQLModel foreign key across schemas 
    # might be tricky for constraints. We map logically or natively.
    user_id: UUID = Field(index=True)  # Logical link to public.users.id
    
    role: UserRole = Field(default=UserRole.STAFF, sa_column=Column(sa.Enum(UserRole, name='tenantuserrole', schema='tenant'), default=UserRole.STAFF, nullable=False))
    branch_id: UUID | None = Field(default=None, index=True)
    is_active: bool = Field(default=True)
