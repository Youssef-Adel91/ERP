"""
app/modules/sales/models/recurring.py — Recurring Invoice Profiles
"""
from datetime import date
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import JSON, Column, Date
from sqlmodel import Field

from app.core.db.base import TenantBase


class RecurringFrequency(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class RecurringStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class RecurringInvoiceProfile(TenantBase, table=True):
    __tablename__ = "recurring_invoice_profiles"
    __table_args__ = ({"schema": "tenant"},)

    customer_id: UUID = Field(index=True)
    frequency: RecurringFrequency = Field(
        sa_column=Column(sa.Enum(RecurringFrequency, name="recurringfrequency", schema="tenant"), nullable=False)
    )
    next_issue_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date | None = Field(default=None, sa_column=Column(Date))
    status: RecurringStatus = Field(
        default=RecurringStatus.ACTIVE,
        sa_column=Column(sa.Enum(RecurringStatus, name="recurringstatus", schema="tenant"), default=RecurringStatus.ACTIVE, nullable=False)
    )
    
    # Was postgresql.dialects.JSONB — switched to generic sa.JSON. Nothing in
    # the codebase used JSONB-specific operators (containment/@>, GIN
    # indexing) on this column, it was only ever read as a plain dict (see
    # services/recurring_worker.py), and every other JSON column project-wide
    # already uses generic JSON — JSONB here was an inconsistency, and it
    # also silently made this table impossible to create on SQLite (blocking
    # the entire pytest suite's shared create_all(), discovered while
    # building the carrier webhook/ETA hardening tests).
    invoice_template_data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
