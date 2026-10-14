"""
app/plugins/purchases/models.py — Purchases Plugin ORM Models (Tenant Schema)

Mirrors the pattern in app/plugins/inventory/models.py (Invoice/InvoiceLine).
These tables live inside `tenant_{id}` via SET search_path — declared with
schema="tenant" and resolved at provisioning time by
provision_tenant_schema()'s schema_translate_map.

Dependency order for CREATE TABLE:
  1. purchase_invoices       (FK -> contacts.id, must come after Contact)
  2. purchase_invoice_lines  (FK -> purchase_invoices.id, items.id)
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Numeric, text
from sqlmodel import Column, Field, Relationship, SQLModel


class PurchaseInvoiceStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    CANCELLED = "cancelled"


class PurchaseInvoice(SQLModel, table=True):
    """A purchase invoice (vendor bill) recorded against a supplier Contact."""

    __tablename__ = "purchase_invoices"
    __table_args__ = (
        Index("ix_purchase_invoices_status", "status"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # FK -> contacts.id (supplier)
    supplier_id: UUID = Field(foreign_key="tenant.contacts.id", index=True)

    invoice_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
    )
    total_amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    status: PurchaseInvoiceStatus = Field(default=PurchaseInvoiceStatus.DRAFT)

    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )

    lines: list["PurchaseInvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )


class PurchaseInvoiceLine(SQLModel, table=True):
    """A single line item on a PurchaseInvoice linking to an Item."""

    __tablename__ = "purchase_invoice_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_invoice_lines_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_purchase_invoice_lines_price"),
        {"schema": "tenant"},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(foreign_key="tenant.purchase_invoices.id", index=True)
    item_id: UUID = Field(foreign_key="tenant.items.id", index=True)
    quantity: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    line_total: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))

    invoice: PurchaseInvoice = Relationship(back_populates="lines")
