"""
app/modules/cases/models/core.py — Generic Case / Process Engine Domain Models

Architecture:
  This engine is the backbone of all multi-vertical plugins (Recruitment, Travel,
  Hospitality, Vehicle Rental). Rather than hardcoding domain logic per vertical,
  each vertical plugin defines a `CaseType` with ordered stages, validation
  schemas per stage, and terminal stages. The engine enforces the configured
  state machine, records immutable history, and publishes events to the EventBus.

  Core principle: Plugins inject configuration (CaseType rows). Core enforces it.
"""
from datetime import date, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase


# ── CaseType — Vertical Plugin Configuration ───────────────────────────────────


class CaseType(TenantBase, table=True):
    """
    Defines a process template for a vertical (e.g. "candidate_deployment",
    "room_reservation", "vehicle_rental").

    Fields:
        code          : Machine-readable slug. Unique per tenant.
        name          : Human-readable label (e.g. "Candidate Deployment").
        stages        : Ordered list of stage definitions.
                        Each stage is a dict:
                        {
                          "id": "screening",          # machine key
                          "label": "Initial Screening",
                          "order": 1,
                          "is_terminal": false,       # set true for CLOSED / CANCELLED
                          "schema": {                 # JSON Schema for validation
                            "type": "object",
                            "properties": { ... }
                          }
                        }
        initial_stage : The `id` of the first stage. Must exist in `stages`.
        plugin_key    : The plugin that owns this type (e.g. "recruitment").
    """

    __tablename__ = "case_types"
    __table_args__ = (
        UniqueConstraint("code", name="uq_case_types_code"),
        {"schema": "tenant"},
    )

    code: str = Field(max_length=100, index=True)
    name: str = Field(max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    plugin_key: str = Field(max_length=100, index=True)
    initial_stage: str = Field(max_length=100)

    # Ordered stage definitions — JSON Array of stage objects
    stages: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default=text("'[]'")),
    )
    # Extra plugin-level metadata (SLA rules, notification templates, etc.)
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )

    cases: list["Case"] = Relationship(back_populates="case_type_rel")


# ── Resource — Bookable Entity ─────────────────────────────────────────────────


class ResourceStatus(str):
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"


class Resource(TenantBase, table=True):
    """
    A bookable entity within a vertical plugin:
      - Hotel room      (Hospitality)
      - Vehicle         (Rental)
      - Candidate slot  (Recruitment)
    """

    __tablename__ = "case_resources"
    __table_args__ = (
        Index("ix_case_resources_type_status", "resource_type", "status"),
        {"schema": "tenant"},
    )

    resource_type: str = Field(max_length=100, index=True)
    name: str = Field(max_length=255)
    code: str | None = Field(default=None, max_length=100, index=True)
    status: str = Field(default="AVAILABLE", max_length=20)

    # Vertical-specific attributes (room number, vehicle plate, etc.)
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )

    cases: list["Case"] = Relationship(back_populates="resource")


# ── Case — The Core Process Instance ──────────────────────────────────────────


class CaseStatus(str):
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class Case(TenantBase, table=True):
    """
    A single running instance of a process (e.g. one candidate deployment,
    one room booking).

    Double-booking prevention is enforced at the service layer using a
    SELECT ... FOR UPDATE advisory lock keyed on (resource_id, overlapping dates).
    PostgreSQL EXCLUDE constraint DDL is emitted separately in a migration.
    """

    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_type_stage", "case_type_id", "current_stage"),
        Index("ix_cases_resource_dates", "resource_id", "start_date", "end_date"),
        Index("ix_cases_status", "status"),
        {"schema": "tenant"},
    )

    case_type_id: UUID = Field(foreign_key="tenant.case_types.id", index=True)
    current_stage: str = Field(max_length=100, index=True)
    status: str = Field(default="ACTIVE", max_length=20)

    # Optional: ties the Case to a bookable Resource
    resource_id: UUID | None = Field(
        default=None, foreign_key="tenant.case_resources.id", index=True
    )
    start_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    end_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))

    # Per-case JSON payload; carries stage-specific validated data
    data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )

    # Denormalised title for list views
    title: str | None = Field(default=None, max_length=500)

    case_type_rel: CaseType | None = Relationship(back_populates="cases")
    resource: Resource | None = Relationship(back_populates="cases")
    contacts: list["CaseContact"] = Relationship(
        back_populates="case",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )
    history: list["CaseStageHistory"] = Relationship(
        back_populates="case",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )


# ── CaseContact — Multi-Role Contact Association ───────────────────────────────


class CaseContact(TenantBase, table=True):
    """
    Links a Case to one or more Contacts with named roles.

    Example roles: "candidate", "sponsor", "guarantor", "guest", "driver".
    Plugins define which roles are meaningful for their CaseType.
    """

    __tablename__ = "case_contacts"
    __table_args__ = (
        UniqueConstraint("case_id", "contact_id", "role", name="uq_case_contacts_case_contact_role"),
        {"schema": "tenant"},
    )

    case_id: UUID = Field(foreign_key="tenant.cases.id", index=True)
    contact_id: UUID = Field(foreign_key="tenant.contacts.id", index=True)
    role: str = Field(max_length=100)
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )

    case: Case = Relationship(back_populates="contacts")


# ── CaseStageHistory — Immutable Audit Log ────────────────────────────────────


class CaseStageHistory(TenantBase, table=True):
    """
    Append-only log of every stage transition on a Case.

    Immutability is enforced at the service layer: rows are never
    updated or deleted. Only INSERT is allowed.
    """

    __tablename__ = "case_stage_history"
    __table_args__ = (
        Index("ix_case_history_case_id", "case_id"),
        {"schema": "tenant"},
    )

    case_id: UUID = Field(foreign_key="tenant.cases.id", index=True)
    from_stage: str | None = Field(default=None, max_length=100)
    to_stage: str = Field(max_length=100)
    changed_by: UUID | None = Field(default=None)
    changed_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    reason: str | None = Field(default=None, max_length=1000)
    # Snapshot of case.data at transition time for full replay capability
    data_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )

    case: Case = Relationship(back_populates="history")
