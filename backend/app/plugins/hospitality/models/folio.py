"""
app/plugins/hospitality/models/folio.py — Folio & Extras Models

FolioItem is the hospitality plugin's only domain model.
It is tenant-isolated via schema provisioning and linked to case_id
(not to a hotel-specific reservation table — the reservation IS the Case).

DECOUPLING CONTRACT:
  ✅ Links to case_id (UUID) by value — no FK to core tables
  ✅ Tenant-isolated via schema provisioning in database.py
  ✅ Never imports from app.modules.accounting

MODEL STYLE: SQLModel (NOT raw SQLAlchemy Mapped[]).
  All fields must use SQLModel's Field() — never Mapped[].
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.core.db.base import TenantBase


class FolioItemCategory(str, enum.Enum):
    ROOM_CHARGE     = "room_charge"      # Generated automatically from daily_rate × nights
    RESTAURANT      = "restaurant"
    LAUNDRY         = "laundry"
    MINIBAR         = "minibar"
    SPA             = "spa"
    TELEPHONE       = "telephone"
    TRANSPORT       = "transport"
    TAX             = "tax"              # VAT line
    SERVICE_CHARGE  = "service_charge"
    DISCOUNT        = "discount"         # Negative amount
    DEPOSIT         = "deposit"          # Negative: offsets total
    OTHER           = "other"


class FolioItem(TenantBase, table=True):
    """
    A single charge line on a hotel reservation's folio.

    Each case (room_reservation) accumulates FolioItem rows over the stay.
    The folio is finalised at checkout: calculate_folio_total() aggregates
    all rows and the listener posts the result to the GL.
    """
    __tablename__ = "folio_items"
    __table_args__ = (
        sa.Index("ix_folio_items_case_date", "case_id", "charge_date"),
        {"schema": "tenant"},
    )

    # Linked to the Case by value (no FK across schemas)
    case_id: uuid.UUID = Field(index=True)

    category: FolioItemCategory = Field(
        sa_column=Column(
            sa.Enum(FolioItemCategory, name="folio_item_category"),
            nullable=False,
        )
    )
    description: str = Field(max_length=500)

    quantity: Decimal = Field(
        default=Decimal("1"),
        sa_column=Column(sa.Numeric(10, 3), nullable=False),
    )
    unit_price: Decimal = Field(
        sa_column=Column(sa.Numeric(14, 4), nullable=False)
    )
    amount: Decimal = Field(
        sa_column=Column(
            sa.Numeric(14, 4),
            nullable=False,
            comment="quantity × unit_price; negative for discounts and deposits",
        )
    )
    currency: str = Field(default="EGP", max_length=3)

    # Date of the charge (may differ from posting date for back-dated items)
    charge_date: datetime = Field(
        sa_column=Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    )
    posted_at: datetime = Field(
        sa_column=Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    )

    posted_by: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, sa_column=Column(sa.Text, nullable=True))
