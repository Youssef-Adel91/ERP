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


class SalesInvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class SalesInvoice(DocumentLifecycleMixin, TenantBase, table=True):
    __tablename__ = "sales_invoices"
    __table_args__ = ({"schema": "tenant"},)

    invoice_number: str = Field(max_length=50, index=True, unique=True)
    # Nullable: service-vertical plugins (Hospitality, Rental) and any other
    # direct/ad-hoc billing flow issue invoices with no preceding SalesOrder.
    # Physical-goods invoices still normally originate from an order via
    # generate_invoice_from_order(), but the model no longer requires it.
    order_id: UUID | None = Field(default=None, index=True, foreign_key="tenant.sales_orders.id")
    contact_id: UUID = Field(index=True)
    status: SalesInvoiceStatus = Field(
        default=SalesInvoiceStatus.DRAFT,
        sa_column=Column(
            sa.Enum(SalesInvoiceStatus, name="salesinvoicestatus", schema="tenant"),
            default=SalesInvoiceStatus.DRAFT,
            nullable=False,
        ),
    )
    issue_date: date = Field(default_factory=date.today, sa_column=Column(Date, nullable=False))
    due_date: date = Field(default_factory=date.today, sa_column=Column(Date, nullable=False))
    currency: str = Field(default="EGP", max_length=3)
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
    lines: list["SalesInvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )


class SalesInvoiceLine(TenantBase, table=True):
    __tablename__ = "sales_invoice_lines"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_sales_invoice_lines_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_sales_invoice_lines_unit_price_non_negative"),
        CheckConstraint("tax_rate >= 0", name="ck_sales_invoice_lines_tax_rate_non_negative"),
        CheckConstraint("tax_amount >= 0", name="ck_sales_invoice_lines_tax_amount_non_negative"),
        {"schema": "tenant"},
    )

    invoice_id: UUID = Field(index=True, foreign_key="tenant.sales_invoices.id")
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    uom_id: UUID | None = Field(default=None, index=True)

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

    invoice: SalesInvoice | None = Relationship(back_populates="lines")
