"""
app/modules/finance/models/settlements.py — Carrier COD Settlement Domain Models (FR-770 to FR-780)

Models:
  - CarrierSettlement: Overall carrier remittance settlement header
  - SettlementLine: Line item per shipment AWB with match state and exception classification
  - CarrierReceivableSnapshot: Aging snapshot for carrier receivables (0-7, 8-14, 15-30, 30+ days)
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class CarrierSettlementState(StrEnum):
    """Lifecycle state of a carrier COD settlement (FR-770)."""

    IMPORTED = "imported"
    MATCHED = "matched"
    PARTIALLY_MATCHED = "partially_matched"
    POSTED = "posted"
    DISPUTED = "disputed"


class SettlementLineMatchState(StrEnum):
    """Match status of an individual settlement AWB line (FR-771, FR-772, FR-774)."""

    MATCHED = "matched"
    FUZZY_MATCHED = "fuzzy_matched"
    UNMATCHED = "unmatched"
    DISPUTED = "disputed"


class SettlementLineExceptionType(StrEnum):
    """Classification of exception for unmatched or disputed lines (FR-774)."""

    NONE = "none"
    REMITTED_BUT_NOT_DELIVERED = "remitted_but_not_delivered"
    AMOUNT_MISMATCH = "amount_mismatch"
    UNKNOWN_AWB = "unknown_awb"
    DUPLICATE_SETTLEMENT = "duplicate_settlement"


class CarrierSettlement(SQLModel, table=True):
    """
    Header record representing an uploaded carrier COD settlement statement (FR-770).
    Reconciles COD remitted by couriers against internal shipments and GL postings.
    """

    __tablename__ = "finance_carrier_settlements"
    # Bug fixed here: this table originally had no schema declared at all,
    # which was assumed to resolve at runtime via the tenant connection's
    # search_path — but app/core/db/database.py's tenant_session() does NOT
    # set search_path; it relies entirely on schema_translate_map={"tenant":
    # schema}, which only rewrites constructs that explicitly declare
    # schema="tenant" (see that function's own docstring: "All models with
    # {"schema": "tenant"} will be routed to the tenant's schema"). Without
    # this, every query compiled to a bare unqualified table name, which
    # Postgres resolved against the connection's actual default search_path
    # ("$user", public — confirmed live), never finding the table even
    # though it existed correctly in the tenant's real schema. Confirmed via
    # a live `GET /finance/settlements` 500 that persisted across a fresh
    # backend restart, ruling out stale connection-pool state.
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    carrier_code: str = Field(index=True, max_length=50)
    settlement_ref: str = Field(index=True, max_length=100)
    gross_amount: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    total_fees: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    net_amount: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    # NOTE: member NAMES are uppercase (IMPORTED, MATCHED, ...) but VALUES are
    # lowercase ("imported", "matched", ...) — same shape as
    # app.modules.finance.models.cheques.ChequeStatus, which needed
    # values_callable to bind each member's `.value` instead of SQLAlchemy's
    # default `.name` binding (a bare sa.Enum(...) here would send "IMPORTED"
    # to Postgres and fail against the lowercase DB enum labels). schema=
    # "tenant" + create_type=False is required regardless of whether the
    # table itself is schema-qualified — see ShiftStatus/EmployeeStatus in
    # this codebase for the same "unqualified enum cast doesn't reliably
    # resolve via search_path" failure mode this avoids. The matching
    # `tenant.carriersettlementstate` type is created explicitly by
    # z6c1a2r3r4i5_add_carrier_settlements_tables.py.
    state: CarrierSettlementState = Field(
        default=CarrierSettlementState.IMPORTED,
        sa_column=Column(
            sa.Enum(
                CarrierSettlementState,
                name="carriersettlementstate",
                schema="tenant",
                create_type=False,
                values_callable=lambda enum_cls: [e.value for e in enum_cls],
            ),
            nullable=False,
            index=True,
        ),
    )
    # Bug fixed here: must be explicitly sa_type=DateTime(timezone=True),
    # matching the same fix already applied to CashShift.opened_at/closed_at
    # (app/modules/pos/models.py) and BaseMixin's created_at/updated_at.
    # Without it, SQLModel infers a bare `DateTime()` (Postgres TIMESTAMP
    # WITHOUT TIME ZONE) regardless of what this migration's column type
    # actually is, while `utc_now()` above returns a tz-aware datetime —
    # asyncpg refuses to encode a tz-aware Python datetime into a naive
    # `timestamp` column: "can't subtract offset-naive and offset-aware
    # datetimes". Confirmed live via a `POST /finance/settlements/match-json`
    # 400 with that exact asyncpg.exceptions.DataError.
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
    posted_at: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
    journal_entry_id: UUID | None = Field(default=None, index=True)


class SettlementLine(SQLModel, table=True):
    """
    Individual AWB remittance record within a carrier settlement statement (FR-771, FR-774).
    """

    __tablename__ = "finance_settlement_lines"
    # See CarrierSettlement.__table_args__ above for why this is required.
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Qualified to match CarrierSettlement now living in schema="tenant" —
    # an unqualified target string here would fail to resolve against the
    # now schema-qualified table at mapper-configuration time.
    settlement_id: UUID = Field(foreign_key="tenant.finance_carrier_settlements.id", index=True)
    shipment_id: UUID | None = Field(default=None, index=True)
    awb_number: str = Field(index=True, max_length=100)
    cod_collected: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    shipping_fee: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    cod_fee: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    return_fee: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    net_remitted: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    # See CarrierSettlement.state above for why values_callable + explicit
    # schema="tenant"/create_type=False are both required here.
    match_state: SettlementLineMatchState = Field(
        default=SettlementLineMatchState.UNMATCHED,
        sa_column=Column(
            sa.Enum(
                SettlementLineMatchState,
                name="settlementlinematchstate",
                schema="tenant",
                create_type=False,
                values_callable=lambda enum_cls: [e.value for e in enum_cls],
            ),
            nullable=False,
            index=True,
        ),
    )
    exception_type: SettlementLineExceptionType = Field(
        default=SettlementLineExceptionType.NONE,
        sa_column=Column(
            sa.Enum(
                SettlementLineExceptionType,
                name="settlementlineexceptiontype",
                schema="tenant",
                create_type=False,
                values_callable=lambda enum_cls: [e.value for e in enum_cls],
            ),
            nullable=False,
            index=True,
        ),
    )
    notes: str = Field(default="", max_length=500)


class CarrierReceivableSnapshot(SQLModel, table=True):
    """
    Aging report snapshot for outstanding COD balances with carrier partners (FR-775).
    Tracks delivered COD shipments that remain unsettled across aging brackets.
    """

    __tablename__ = "finance_carrier_receivable_snapshots"
    # See CarrierSettlement.__table_args__ above for why this is required.
    __table_args__ = {"schema": "tenant"}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    carrier_code: str = Field(index=True, max_length=50)
    snapshot_date: date = Field(default_factory=date.today, index=True)
    total_outstanding_cod: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    unsettled_shipments_count: int = Field(default=0)
    aging_0_7_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    aging_8_14_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    aging_15_30_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    aging_30_plus_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
