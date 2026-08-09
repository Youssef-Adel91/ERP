"""
app.modules.pos.models — Point of Sale: Cash Shifts & Sale Ledger (Phase 6, built from scratch)

Deliberately minimal (per explicit instruction: "minimal but solid API
surface"). POS does NOT duplicate invoicing/inventory/accounting logic —
a POS sale IS a SalesInvoice, created via the same
app.modules.sales.services.invoicing.create_adhoc_invoice() +
post_invoice() pipeline every other ad-hoc billing flow (Hospitality
folio, Rental close-out) uses, so it correctly hits the ledger and stock
consumption exactly like any other sale.

Two tenant-schema tables:
  - CashShift: one cashier session, opening/closing cash reconciliation.
  - PosSale: a thin join row linking a shift to the SalesInvoice it
    produced, so shift totals/reporting don't require guessing from
    SalesInvoice.created_at/created_by.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Numeric
from sqlmodel import Field

from app.core.db.base import TenantBase


class ShiftStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class CashShift(TenantBase, table=True):
    """One cashier's till session, from open to close."""
    __tablename__ = "pos_cash_shifts"
    __table_args__ = ({"schema": "tenant"},)

    opened_by: UUID = Field(index=True)
    closed_by: UUID | None = Field(default=None)
    status: ShiftStatus = Field(default=ShiftStatus.OPEN, index=True)

    opening_balance: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    closing_balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 4), nullable=True))
    # opening_balance + all POS sale amounts recorded against this shift.
    # NOTE: assumes cash-only sales for now — payment_method-aware cash
    # reconciliation (excluding card/COD from the expected cash figure) is
    # a follow-up once a real payment method taxonomy exists at checkout.
    expected_balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 4), nullable=True))
    variance: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 4), nullable=True))

    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = Field(default=None)


class PosSale(TenantBase, table=True):
    """Links a completed checkout (SalesInvoice) to the shift it was rung under."""
    __tablename__ = "pos_sales"
    __table_args__ = ({"schema": "tenant"},)

    shift_id: UUID = Field(index=True, foreign_key="tenant.pos_cash_shifts.id")
    invoice_id: UUID = Field(index=True, foreign_key="tenant.sales_invoices.id")
    cashier_id: UUID = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    payment_method: str = Field(default="cash", max_length=30)
