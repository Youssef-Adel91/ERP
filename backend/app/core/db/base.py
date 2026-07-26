"""
app/core/db/base.py — Declarative SQLModel Bases

PgBouncer-safe multi-tenancy via schema_translate_map
------------------------------------------------------

  OLD approach (unsafe with transaction pooling):
    SET search_path TO tenant_<uuid>
    → mutates connection-level state that leaks across pool reuse

  NEW approach (safe):
    session.connection(execution_options={
        "schema_translate_map": {"tenant": "tenant_<uuid>"}
    })
    → query-level rewrite, no connection state mutation

PublicBase
----------
  Base for global entities: Tenant, User, Subscription.
  Subclasses set {"schema": "public"} in __table_args__ so SQLAlchemy
  always qualifies SQL as `public.tenants`, `public.users`, etc.
  These are never subject to schema translation.

TenantBase
----------
  Base for per-merchant entities: Account, Contact, Item, Invoice, ...
  Subclasses set {"schema": "tenant"} in __table_args__. The literal
  string "tenant" is the SYMBOLIC schema key translated by schema_translate_map:

    {"tenant": "tenant_550e8400_e29b_41d4_a716_446655440000"}

  SQLAlchemy generates:
    SELECT * FROM tenant_550e8400_....accounts
  instead of:
    SELECT * FROM tenant.accounts

Usage
-----
  class MyPublicModel(PublicBase, table=True):
      __table_args__ = (UniqueConstraint("col"), {"schema": "public"})
      ...

  class MyTenantModel(TenantBase, table=True):
      __table_args__ = (Index("ix_...", "col"), {"schema": "tenant"})
      ...
"""
from datetime import datetime
from uuid import UUID

import uuid6
from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


class BaseMixin(SQLModel):
    """
    Uniform base fields for all models across the ERP system.
    Uses UUIDv7 for time-sortable primary keys.
    """
    id: UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    created_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now(), "nullable": False},
    )
    created_by: UUID | None = Field(default=None)
    updated_by: UUID | None = Field(default=None)
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )


class PublicBase(BaseMixin):
    """Base class for all public-schema models (global entities)."""

    class Config:
        # Subclasses must set table=True and include {"schema": "public"}
        # in __table_args__
        pass


class TenantBase(BaseMixin):
    """
    Base class for all per-tenant models.

    Subclasses must set table=True and include {"schema": "tenant"} in
    __table_args__. The "tenant" string is the symbolic key that
    schema_translate_map rewrites to the real schema at query time.
    """

    class Config:
        pass

