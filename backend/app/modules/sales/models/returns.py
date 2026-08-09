from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Date, Numeric, text
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin
from app.modules.sales.models.core import SalesOrder
from app.modules.sales.models.invoice import SalesInvoice


class SalesReturnStatus(StrEnum):
    DRAFT = "DRAFT"
    RECEIVED = "RECEIVED"
    CREDITED = "CREDITED"


class SalesReturn(DocumentLifecycleMixin, TenantBase, table=True):
    __tablename__ = "sales_returns"
    __table_args__ = ({"schema": "tenant"},)

    return_number: str = Field(max_length=50, index=True, unique=True)
    order_id: UUID | None = Field(default=None, index=True, foreign_key="tenant.sales_orders.id")
    invoice_id: UUID = Field(index=True, foreign_key="tenant.sales_invoices.id")
    contact_id: UUID = Field(index=True)
    credit_note_id: UUID | None = Field(default=None, index=True, foreign_key="tenant.sales_invoices.id")

    status: SalesReturnStatus = Field(
        default=SalesReturnStatus.DRAFT,
        sa_column=Column(
            sa.Enum(SalesReturnStatus, name="salesreturnstatus", schema="tenant"),
            default=SalesReturnStatus.DRAFT,
            nullable=False,
        ),
    )
    return_date: date = Field(default_factory=date.today, sa_column=Column(Date, nullable=False))
    subtotal: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(18, 4), nullable=False)
    )
    tax_total: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(18, 4), nullable=False)
    )
    grand_total: Decimal = Field(
        default=Decimal("0.0000"), sa_column=Column(Numeric(18, 4), nullable=False)
    )

    order: SalesOrder | None = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    invoice: SalesInvoice | None = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "foreign_keys": "SalesReturn.invoice_id"},
    )
    credit_note: SalesInvoice | None = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "foreign_keys": "SalesReturn.credit_note_id"},
    )
    lines: list["SalesReturnLine"] = Relationship(
        back_populates="sales_return",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )


class SalesReturnLine(TenantBase, table=True):
    __tablename__ = "sales_return_lines"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_sales_return_lines_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sales_return_lines_unit_price_non_negative"),
        CheckConstraint("tax_rate >= 0", name="ck_sales_return_lines_tax_rate_non_negative"),
        CheckConstraint("tax_amount >= 0", name="ck_sales_return_lines_tax_amount_non_negative"),
        {"schema": "tenant"},
    )

    return_id: UUID = Field(index=True, foreign_key="tenant.sales_returns.id")
    original_invoice_line_id: UUID = Field(index=True, foreign_key="tenant.sales_invoice_lines.id")
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    uom_id: UUID | None = Field(default=None, index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    serial_id: UUID | None = Field(default=None, index=True)

    qty: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    line_total: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    tax_rate: Decimal = Field(
        default=Decimal("0.1400"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0.1400")),
    )
    tax_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0.0000")),
    )

    sales_return: SalesReturn | None = Relationship(back_populates="lines")
