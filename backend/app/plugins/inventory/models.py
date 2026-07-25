"""
app/plugins/inventory/models.py — Inventory Plugin ORM Models (Tenant Schema)

No `schema=` annotation — these tables are created inside the tenant schema
by provision_tenant_schema() via SET search_path.

Dependency order for CREATE TABLE (FKs must come after referenced tables):
  1. items       (no FK dependencies in tenant schema)
  2. invoices    (FK → contacts.id — contacts table must exist first)
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Numeric, UniqueConstraint, text
from sqlmodel import Column, Field, Relationship, SQLModel


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    CANCELLED = "cancelled"


# ── Item (Stock-Keeping Unit) ─────────────────────────────────────────────────


class Item(SQLModel, table=True):
    """
    A sellable or purchasable item in the merchant's catalogue.

    Intentionally kept flat (no variants, bundles, or composite items in MVP).
    These will be added as plugin extensions in a future sprint.
    """

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_items_sku"),
        CheckConstraint(
            "price >= 0 AND quantity_on_hand >= 0",
            name="ck_items_non_negative",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255, index=True)
    name_ar: str | None = Field(default=None, max_length=255)
    sku: str = Field(max_length=100, index=True)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)

    # Financials
    price: Decimal = Field(
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
    cost: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )

    # Stock
    quantity_on_hand: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )
    reorder_level: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )

    is_active: bool = Field(default=True)
    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )

    # Line items on this product
    invoice_lines: list["InvoiceLine"] = Relationship(back_populates="item")


# ── Invoice ───────────────────────────────────────────────────────────────────


class Invoice(SQLModel, table=True):
    """
    A sales invoice issued to a Contact (Customer).

    On creation:
      1. Invoice row is inserted and committed (gets a real UUID).
      2. An `invoice.created` DomainEvent is published to the EventBus.
      3. The accounting event handler picks it up and inserts a balanced
         JournalEntry (DR Accounts Receivable / CR Sales Revenue) into
         the same tenant schema.

    The Invoice and JournalEntry are linked via source_id in JournalEntry,
    but there is NO direct FK between the two tables — loose coupling.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_number"),
        Index("ix_invoices_status", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Human-readable invoice number (auto-generated in service layer)
    invoice_number: str = Field(max_length=50, index=True)

    # FK → contacts.id (same tenant schema, no schema prefix needed)
    # NOTE: contact_id references the contacts table via SET search_path
    contact_id: UUID = Field(foreign_key="contacts.id", index=True)

    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT)

    total_amount: Decimal = Field(
        sa_column=Column(Numeric(18, 4), nullable=False)
    )

    notes: str | None = Field(default=None, max_length=2000)

    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )

    # Relationships
    contact: "Contact" = Relationship(  # noqa: F821
        back_populates="invoices",
        sa_relationship_kwargs={"lazy": "select"},
    )
    lines: list["InvoiceLine"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


# ── Invoice Line ──────────────────────────────────────────────────────────────


class InvoiceLine(SQLModel, table=True):
    """A single line item on an Invoice linking to an Item."""

    __tablename__ = "invoice_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_lines_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_lines_price"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(foreign_key="invoices.id", index=True)
    item_id: UUID = Field(foreign_key="items.id", index=True)
    quantity: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    unit_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    total_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))

    invoice: Invoice = Relationship(back_populates="lines")
    item: Item = Relationship(back_populates="invoice_lines")


# ── Import Contact here for FK resolution (avoids circular import) ────────────
# SQLAlchemy resolves string FK "contacts.id" at table creation time via
# the active search_path. No Python import needed for FK column definition.
# The `Invoice.contact` relationship uses a string annotation to break the cycle.
from app.modules.contacts.models import Contact  # noqa: E402, F401
