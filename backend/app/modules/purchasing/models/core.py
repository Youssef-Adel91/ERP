"""
app/modules/purchasing/models/core.py — Purchasing & Receiving ORM Models

Defines:
  1. PurchaseOrder (inherits DocumentLifecycleMixin)
  2. PurchaseOrderLine (with strict invariant qty_received <= qty_ordered)
  3. GoodsReceipt (GRN - inherits DocumentLifecycleMixin)
  4. GoodsReceiptLine
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Date, Numeric
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin


class PurchaseOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    BILLED = "BILLED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class GoodsReceiptStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class PurchaseOrder(DocumentLifecycleMixin, TenantBase, table=True):
    __tablename__ = "purchase_orders"
    __table_args__ = ({"schema": "tenant"},)

    po_number: str = Field(max_length=50, index=True, unique=True)
    supplier_id: UUID = Field(index=True)
    order_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    expected_date: date | None = Field(
        default=None,
        sa_column=Column(Date, nullable=True),
    )
    currency: str = Field(default="EGP", max_length=3)
    fx_rate: Decimal = Field(
        default=Decimal("1.0000"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="1.0000"),
    )
    branch_id: UUID | None = Field(default=None, index=True)
    warehouse_id: UUID = Field(index=True)
    total_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    status: PurchaseOrderStatus = Field(
        default=PurchaseOrderStatus.DRAFT,
        sa_column=Column(
            sa.Enum(PurchaseOrderStatus, name="purchaseorderstatus", schema="tenant"),
            default=PurchaseOrderStatus.DRAFT,
            nullable=False,
        ),
    )

    lines: list["PurchaseOrderLine"] = Relationship(
        back_populates="po",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )
    receipts: list["GoodsReceipt"] = Relationship(
        back_populates="po",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class PurchaseOrderLine(TenantBase, table=True):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("qty_received <= qty_ordered", name="ck_po_line_qty_received_le_ordered"),
        CheckConstraint("qty_ordered >= 0", name="ck_po_line_qty_ordered_non_neg"),
        CheckConstraint("qty_received >= 0", name="ck_po_line_qty_received_non_neg"),
        {"schema": "tenant"},
    )

    po_id: UUID = Field(
        foreign_key="tenant.purchase_orders.id",
        index=True,
    )
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    qty_ordered: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    qty_received: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    qty_billed: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    unit_price: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    expected_landed_unit_cost: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 4), nullable=True),
    )

    po: Optional["PurchaseOrder"] = Relationship(back_populates="lines")


class GoodsReceipt(DocumentLifecycleMixin, TenantBase, table=True):
    __tablename__ = "goods_receipts"
    __table_args__ = ({"schema": "tenant"},)

    po_id: UUID | None = Field(
        default=None,
        foreign_key="tenant.purchase_orders.id",
        index=True,
    )
    supplier_id: UUID = Field(index=True)
    grn_number: str = Field(max_length=50, index=True, unique=True)
    receipt_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    warehouse_id: UUID = Field(index=True)
    branch_id: UUID | None = Field(default=None, index=True)
    supplier_delivery_ref: str | None = Field(default=None, max_length=100)
    status: GoodsReceiptStatus = Field(
        default=GoodsReceiptStatus.DRAFT,
        sa_column=Column(
            sa.Enum(GoodsReceiptStatus, name="goodsreceiptstatus", schema="tenant"),
            default=GoodsReceiptStatus.DRAFT,
            nullable=False,
        ),
    )

    po: Optional["PurchaseOrder"] = Relationship(back_populates="receipts")
    lines: list["GoodsReceiptLine"] = Relationship(
        back_populates="grn",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )


class GoodsReceiptLine(TenantBase, table=True):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        CheckConstraint("qty_received >= 0", name="ck_grn_line_qty_received_non_neg"),
        {"schema": "tenant"},
    )

    grn_id: UUID = Field(
        foreign_key="tenant.goods_receipts.id",
        index=True,
    )
    po_line_id: UUID | None = Field(
        default=None,
        foreign_key="tenant.purchase_order_lines.id",
        index=True,
    )
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    qty_received: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    qty_rejected: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    batch_id: UUID | None = Field(default=None, index=True)
    serial_ids: list[str] | None = Field(
        default=None,
        sa_column=Column(sa.JSON, nullable=True),
    )
    unit_cost_estimated: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    expected_landed_unit_cost: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 4), nullable=True),
    )

    grn: Optional["GoodsReceipt"] = Relationship(back_populates="lines")
