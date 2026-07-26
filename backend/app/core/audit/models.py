"""
app/core/audit/models.py — Immutable Audit Log Model

This model is protected at the database level by PostgreSQL RULE objects
injected via Alembic migration, making UPDATE and DELETE physically impossible:

    CREATE RULE audit_no_update AS ON UPDATE TO <schema>.audit_logs
        DO INSTEAD NOTHING;
    CREATE RULE audit_no_delete AS ON DELETE TO <schema>.audit_logs
        DO INSTEAD NOTHING;

This means even a superuser cannot silently alter audit records without
first dropping the rules — which itself is an auditable DDL event.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, Index
from sqlmodel import Field

from app.core.db.base import TenantBase


class AuditSource(StrEnum):
    UI = "ui"
    API = "api"
    AI_ASSISTED = "ai_assisted"
    SYSTEM_EVENT = "system_event"
    IMPORT = "import"


class AuditLog(TenantBase, table=True):
    """
    Append-only audit trail for all state-changing operations.

    Database-level immutability is enforced by PostgreSQL RULE objects installed
    during the tenant schema migration. Application code MUST only ever INSERT
    into this table — never UPDATE or DELETE.

    Inherits: id (UUIDv7), created_at, updated_at, created_by, updated_by, deleted_at
    Uses created_at as occurred_at (the BaseMixin timestamp of insertion = audit timestamp).
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor", "actor_id"),
        Index("ix_audit_logs_occurred_at", "created_at"),
        {"schema": "tenant", "extend_existing": True},
    )

    # WHO
    actor_id: UUID | None = Field(default=None, nullable=True)
    actor_type: str = Field(default="user", max_length=50)  # "user", "system", "worker"

    # WHAT
    action: str = Field(max_length=100)           # "create", "update", "post", "void", etc.
    entity_type: str = Field(max_length=100)      # "JournalEntry", "Invoice", "Contact", etc.
    entity_id: UUID | None = Field(default=None, nullable=True)

    # HOW
    source: AuditSource = Field(
        default=AuditSource.API,
        sa_column=Column(
            sa.Enum(AuditSource, name="auditsource", schema="tenant"),
            nullable=False,
        ),
    )
    ip_address: str | None = Field(default=None, max_length=45)  # IPv4 or IPv6
    user_agent: str | None = Field(default=None, max_length=512)

    # STATE DIFF (JSONB for PostgreSQL, JSON for SQLite in tests)
    before_state: dict | None = Field(
        default=None,
        sa_column=Column(sa.JSON, nullable=True),
    )
    after_state: dict | None = Field(
        default=None,
        sa_column=Column(sa.JSON, nullable=True),
    )
