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

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Numeric
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
    # NOTE: must be explicitly schema-qualified via sa.Enum(..., schema="tenant"),
    # matching JournalEntryStatus/AccountType/DocumentState/etc. elsewhere in the
    # codebase. The "tenant" schema token is rewritten to the real
    # tenant_<uuid> schema at query-compile time by the schema_translate_map
    # listener (see app/core/db/base.py). Without an explicit schema= here,
    # SQLModel auto-infers a bare `sa.Enum(ShiftStatus)` with no schema, so
    # generated SQL casts parameters as unqualified `$2::shiftstatus` — which
    # only resolves if "shiftstatus" happens to be on the connection's
    # search_path, which it is not. That produced
    # `asyncpg.exceptions.UndefinedObjectError: type "shiftstatus" does not
    # exist` even though the type exists (correctly) inside each tenant
    # schema, created by 99f91dd227cd_add_missing_tenant_models.py.
    # create_type=False because the enum type is already created by that
    # migration; SQLAlchemy/Alembic must never try to CREATE TYPE it again.
    status: ShiftStatus = Field(
        default=ShiftStatus.OPEN,
        sa_column=Column(
            sa.Enum(ShiftStatus, name="shiftstatus", schema="tenant", create_type=False),
            nullable=False,
            index=True,
        ),
    )

    opening_balance: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    closing_balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 4), nullable=True))
    # opening_balance + all POS sale amounts recorded against this shift.
    # NOTE: assumes cash-only sales for now — payment_method-aware cash
    # reconciliation (excluding card/COD from the expected cash figure) is
    # a follow-up once a real payment method taxonomy exists at checkout.
    expected_balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 4), nullable=True))
    variance: Decimal | None = Field(default=None, sa_column=Column(Numeric(18, 4), nullable=True))

    # NOTE: must be explicitly sa_type=DateTime(timezone=True), matching
    # created_at/updated_at/deleted_at on BaseMixin (app/core/db/base.py)
    # and how this exact table's own created_at/updated_at were created
    # (99f91dd227cd_add_missing_tenant_models.py). Without timezone=True,
    # SQLModel infers a bare `DateTime()` (Postgres `TIMESTAMP WITHOUT TIME
    # ZONE`), while both open_shift()/close_shift() (app/modules/pos/api.py)
    # construct these values with `datetime.now(UTC)` — tz-aware. asyncpg
    # refuses to encode a tz-aware Python datetime into a naive `timestamp`
    # column: "can't subtract offset-naive and offset-aware datetimes".
    # Column type fixed to TIMESTAMP WITH TIME ZONE by migration
    # t0o5p6q7r8s9_fix_pos_cash_shifts_timestamp_tz.py.
    opened_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
    closed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )


class PosSale(TenantBase, table=True):
    """Links a completed checkout (SalesInvoice) to the shift it was rung under."""
    __tablename__ = "pos_sales"
    __table_args__ = ({"schema": "tenant"},)

    shift_id: UUID = Field(index=True, foreign_key="tenant.pos_cash_shifts.id")
    invoice_id: UUID = Field(index=True, foreign_key="tenant.sales_invoices.id")
    cashier_id: UUID = Field(index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    payment_method: str = Field(default="cash", max_length=30)
