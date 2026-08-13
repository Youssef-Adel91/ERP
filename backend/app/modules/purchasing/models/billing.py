"""
app/modules/purchasing/models/billing.py — Vendor Bills & Three-Way Match Models

Defines:
  1. VendorBill (inherits DocumentLifecycleMixin & TenantBase)
  2. VendorBillLine
  3. ThreeWayMatchResult (immutable audit trail for match variance assertions)
  4. VendorBillMatchState and VendorBillStatus enums
"""
from datetime import date, datetime, UTC
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, Date, DateTime, Numeric, String, func
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin, DocumentState


class VendorBillMatchState(StrEnum):
    UNMATCHED = "UNMATCHED"
    MATCHED = "MATCHED"
    VARIANCE_WITHIN_TOLERANCE = "VARIANCE_WITHIN_TOLERANCE"
    VARIANCE_BLOCKED = "VARIANCE_BLOCKED"


class VendorBillStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class VendorBill(DocumentLifecycleMixin, TenantBase, table=True):
    """
    Vendor Bill document representing vendor invoice received for PO / GRN receipts.
    Must undergo a strict Three-Way Match before posting to AP.
    """

    __tablename__ = "vendor_bills"
    __table_args__ = ({"schema": "tenant"},)

    bill_number: str = Field(max_length=50, index=True, unique=True)
    supplier_id: UUID = Field(index=True)
    bill_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    due_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    currency: str = Field(default="EGP", max_length=3)
    fx_rate: Decimal = Field(
        default=Decimal("1.000000"),
        sa_column=Column(Numeric(18, 6), nullable=False),
    )
    branch_id: UUID | None = Field(default=None, index=True)

    # NOTE: these override DocumentLifecycleMixin's/plain sa.Enum declarations with
    # explicit String columns. The actual migration (f6a1b2c3d4e5) created
    # match_state/status/state as plain VARCHAR, not native Postgres enum types.
    # A bare sa.Enum(...) here (no name=/schema=/create_type=False) makes SQLAlchemy
    # look up a native enum type OID via asyncpg that was never created, causing
    # "type ... does not exist" 500s. Match the deployed column types instead.
    match_state: VendorBillMatchState = Field(
        default=VendorBillMatchState.UNMATCHED,
        sa_column=Column(String(30), nullable=False),
    )
    status: VendorBillStatus = Field(
        default=VendorBillStatus.DRAFT,
        sa_column=Column(String(30), nullable=False),
    )
    state: DocumentState = Field(
        default=DocumentState.DRAFT,
        sa_column=Column(String(30), nullable=False),
    )
    subtotal: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    tax_total: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    total_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )

    lines: list["VendorBillLine"] = Relationship(
        back_populates="bill",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class VendorBillLine(TenantBase, table=True):
    """
    Line item for a VendorBill, optionally linked to a PurchaseOrderLine and/or GoodsReceiptLine.
    """

    __tablename__ = "vendor_bill_lines"
    __table_args__ = ({"schema": "tenant"},)

    bill_id: UUID = Field(foreign_key="tenant.vendor_bills.id", index=True)
    po_line_id: UUID | None = Field(default=None, index=True)
    grn_line_id: UUID | None = Field(default=None, index=True)

    qty_billed: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    unit_price: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    tax_code_id: UUID | None = Field(default=None, index=True)

    bill: Optional[VendorBill] = Relationship(back_populates="lines")


class ThreeWayMatchResult(TenantBase, table=True):
    """
    Immutable audit record for Three-Way Match (PO vs. GRN vs. Bill) execution results per line.
    """

    __tablename__ = "three_way_match_results"
    __table_args__ = ({"schema": "tenant"},)

    bill_id: UUID = Field(index=True)
    bill_line_id: UUID = Field(index=True)

    qty_variance: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    price_variance: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    is_within_tolerance: bool = Field(default=False)

    matched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
