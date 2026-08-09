from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Date, Numeric, text
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase


class SalesOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    FULFILLED = "FULFILLED"
    INVOICED = "INVOICED"
    CANCELLED = "CANCELLED"


class SalesOrder(TenantBase, table=True):
    __tablename__ = "sales_orders"
    __table_args__ = ({"schema": "tenant"},)

    order_number: str = Field(max_length=50, index=True, unique=True)
    contact_id: UUID = Field(index=True)
    status: SalesOrderStatus = Field(
        default=SalesOrderStatus.DRAFT,
        sa_column=Column(
            sa.Enum(SalesOrderStatus, name="salesorderstatus", schema="tenant"),
            default=SalesOrderStatus.DRAFT,
            nullable=False,
        ),
    )
    order_date: date = Field(default_factory=date.today, sa_column=Column(Date, nullable=False))
    currency: str = Field(default="EGP", max_length=3)
    total_amount: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(18, 4), nullable=False)
    )

    lines: list["SalesOrderLine"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )


class SalesOrderLine(TenantBase, table=True):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_sales_order_lines_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sales_order_lines_unit_price_non_negative"),
        CheckConstraint("fulfilled_qty >= 0", name="ck_sales_order_lines_fulfilled_qty_non_negative"),
        {"schema": "tenant"},
    )

    order_id: UUID = Field(index=True, foreign_key="tenant.sales_orders.id")
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    uom_id: UUID | None = Field(default=None, index=True)

    qty: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    fulfilled_qty: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )
    unit_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    line_total: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))

    order: SalesOrder | None = Relationship(back_populates="lines")
