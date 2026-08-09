"""
app/plugins/sales/models.py — Sales Plugin ORM Models (Tenant Schema)

Distinct from app/plugins/inventory/models.py::Invoice — this is the
dedicated Sales Invoice used by the Sales Plugin router (customer_id,
stock deduction on confirm). Mirrors the same SQLModel/tenant-schema
pattern used across the codebase.

Dependency order for CREATE TABLE:
  1. sales_invoices       (FK -> contacts.id, must come after Contact)
  2. sales_invoice_lines  (FK -> sales_invoices.id, items.id)
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Numeric, text
from sqlmodel import Column, Field, Relationship, SQLModel


class SalesInvoiceStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    CANCELLED = "cancelled"


class SalesInvoice(SQLModel, table=True):
    """A sales invoice issued to a customer Contact via the Sales Plugin."""

    __tablename__ = "sales_invoices"
    __table_args__ = (
        Index("ix_sales_invoices_status", "status"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # FK -> contacts.id (customer)
    customer_id: UUID = Field(foreign_key="tenant.contacts.id", index=True)

    invoice_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
    total_amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    status: SalesInvoiceStatus = Field(default=SalesInvoiceStatus.DRAFT)
    notes: str | None = Field(default=None, max_length=2000)

    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )

    lines: list["SalesInvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )


class SalesInvoiceLine(SQLModel, table=True):
    """A single line item on a SalesInvoice linking to an Item."""

    __tablename__ = "sales_invoice_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_invoice_lines_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_sales_invoice_lines_price"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(foreign_key="tenant.sales_invoices.id", index=True)
    item_id: UUID = Field(foreign_key="tenant.items.id", index=True)
    quantity: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    line_total: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))

    invoice: SalesInvoice = Relationship(back_populates="lines")
