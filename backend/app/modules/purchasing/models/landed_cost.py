"""
app/modules/purchasing/models/landed_cost.py — Import Shipments & Landed Cost Allocation Models

Defines:
  1. ImportShipment (inherits DocumentLifecycleMixin & TenantBase)
  2. LandedCostLine (individual cost items e.g., freight, customs, insurance)
  3. LandedCostAllocation (piastre-exact allocated landed cost per GRN line)
  4. Enums: ImportShipmentStage, ImportShipmentStatus, LandedCostType, AllocationBasis
"""
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, Numeric
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin


class ImportShipmentStage(StrEnum):
    DRAFT = "DRAFT"
    SHIPPED = "SHIPPED"
    CLEARED = "CLEARED"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"


class ImportShipmentStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class LandedCostType(StrEnum):
    FREIGHT = "FREIGHT"
    CUSTOMS = "CUSTOMS"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class AllocationBasis(StrEnum):
    VALUE = "VALUE"
    WEIGHT = "WEIGHT"
    VOLUME = "VOLUME"
    QTY = "QTY"


class ImportShipment(DocumentLifecycleMixin, TenantBase, table=True):
    """
    Import Shipment document representing an inbound international shipment
    grouping multiple purchase orders/suppliers and associated landed costs.
    """

    __tablename__ = "import_shipments"
    __table_args__ = ({"schema": "tenant"},)

    shipment_ref: str = Field(max_length=50, index=True, unique=True)
    supplier_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(sa.JSON, nullable=False, server_default="[]"),
    )
    po_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(sa.JSON, nullable=False, server_default="[]"),
    )
    stage: ImportShipmentStage = Field(
        default=ImportShipmentStage.DRAFT,
        sa_column=Column(
            sa.Enum(ImportShipmentStage, name="importshipmentstage", schema="tenant"),
            default=ImportShipmentStage.DRAFT,
            nullable=False,
        ),
    )
    status: ImportShipmentStatus = Field(
        default=ImportShipmentStatus.DRAFT,
        sa_column=Column(
            sa.Enum(ImportShipmentStatus, name="importshipmentstatus", schema="tenant"),
            default=ImportShipmentStatus.DRAFT,
            nullable=False,
        ),
    )
    currency: str = Field(default="EGP", max_length=10)
    fx_rate: Decimal = Field(
        default=Decimal("1.0000"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="1.000000"),
    )
    total_landed_cost: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default="0.0000"),
    )

    lines: list["LandedCostLine"] = Relationship(back_populates="shipment")


class LandedCostLine(TenantBase, table=True):
    """
    Individual landed cost item (e.g. freight invoice, customs fees, insurance)
    to be allocated across target GRN lines.
    """

    __tablename__ = "landed_cost_lines"
    __table_args__ = ({"schema": "tenant"},)

    shipment_id: UUID = Field(foreign_key="tenant.import_shipments.id", index=True)
    cost_type: LandedCostType = Field(
        default=LandedCostType.FREIGHT,
        sa_column=Column(
            sa.Enum(LandedCostType, name="landedcosttype", schema="tenant"),
            nullable=False,
        ),
    )
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    currency: str = Field(default="EGP", max_length=10)
    fx_rate: Decimal = Field(
        default=Decimal("1.0000"),
        sa_column=Column(Numeric(18, 6), nullable=False, server_default="1.000000"),
    )
    allocation_basis: AllocationBasis = Field(
        default=AllocationBasis.VALUE,
        sa_column=Column(
            sa.Enum(AllocationBasis, name="allocationbasis", schema="tenant"),
            nullable=False,
        ),
    )

    shipment: Optional["ImportShipment"] = Relationship(back_populates="lines")
    allocations: list["LandedCostAllocation"] = Relationship(back_populates="landed_cost_line")


class LandedCostAllocation(TenantBase, table=True):
    """
    Exact piastre allocation of a landed cost line to a target Goods Receipt Line,
    calculated via the Largest Remainder Method.
    """

    __tablename__ = "landed_cost_allocations"
    __table_args__ = ({"schema": "tenant"},)

    landed_cost_line_id: UUID = Field(foreign_key="tenant.landed_cost_lines.id", index=True)
    target_grn_line_id: UUID = Field(foreign_key="tenant.goods_receipt_lines.id", index=True)
    allocated_amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))

    landed_cost_line: Optional["LandedCostLine"] = Relationship(back_populates="allocations")
