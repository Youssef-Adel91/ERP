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

from sqlmodel import Field, SQLModel


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

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    carrier_code: str = Field(index=True, max_length=50)
    settlement_ref: str = Field(index=True, max_length=100)
    gross_amount: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    total_fees: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    net_amount: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    state: CarrierSettlementState = Field(
        default=CarrierSettlementState.IMPORTED,
        index=True,
    )
    created_at: datetime = Field(default_factory=utc_now)
    posted_at: datetime | None = Field(default=None)
    journal_entry_id: UUID | None = Field(default=None, index=True)


class SettlementLine(SQLModel, table=True):
    """
    Individual AWB remittance record within a carrier settlement statement (FR-771, FR-774).
    """

    __tablename__ = "finance_settlement_lines"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    settlement_id: UUID = Field(foreign_key="finance_carrier_settlements.id", index=True)
    shipment_id: UUID | None = Field(default=None, index=True)
    awb_number: str = Field(index=True, max_length=100)
    cod_collected: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    shipping_fee: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    cod_fee: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    return_fee: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    net_remitted: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    match_state: SettlementLineMatchState = Field(
        default=SettlementLineMatchState.UNMATCHED,
        index=True,
    )
    exception_type: SettlementLineExceptionType = Field(
        default=SettlementLineExceptionType.NONE,
        index=True,
    )
    notes: str = Field(default="", max_length=500)


class CarrierReceivableSnapshot(SQLModel, table=True):
    """
    Aging report snapshot for outstanding COD balances with carrier partners (FR-775).
    Tracks delivered COD shipments that remain unsettled across aging brackets.
    """

    __tablename__ = "finance_carrier_receivable_snapshots"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    carrier_code: str = Field(index=True, max_length=50)
    snapshot_date: date = Field(default_factory=date.today, index=True)
    total_outstanding_cod: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    unsettled_shipments_count: int = Field(default=0)
    aging_0_7_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    aging_8_14_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    aging_15_30_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
    aging_30_plus_days: Decimal = Field(default=Decimal("0.00"), max_digits=15, decimal_places=4)
