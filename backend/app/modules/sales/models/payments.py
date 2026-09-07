"""
app/modules/sales/models/payments.py — Customer (Sales) Payments & Payment Allocations

Wave 3 item 1: mirrors app/modules/purchasing/models/payments.py exactly, but
for the Accounts Receivable side (customer -> tenant), instead of Accounts
Payable (tenant -> supplier). No FX handling — sales payments are recorded
in the invoice's own currency only (EGP by default), which keeps this a
straight, safe addition with no schema changes to any other module.

Defines:
  1. SalesPayment (inherits DocumentLifecycleMixin & TenantBase)
  2. SalesPaymentAllocation (links SalesPayment to SalesInvoice)
  3. SalesPaymentStatus enum
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, Date, Numeric
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin
from app.modules.sales.models.invoice import SalesInvoice


class SalesPaymentStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class SalesPayment(DocumentLifecycleMixin, TenantBase, table=True):
    """
    Customer payment received against one or more posted SalesInvoices.
    """

    __tablename__ = "sales_payments"
    __table_args__ = ({"schema": "tenant"},)

    payment_number: str = Field(max_length=50, index=True, unique=True)
    contact_id: UUID = Field(index=True)
    # Optional GL Account (tenant.accounts.id) the cash/bank leg is posted
    # to. When absent, the GL consumer falls back to the tenant's default
    # Cash & Banks mapping — same fallback pattern as purchasing payments'
    # treasury_id.
    treasury_id: UUID | None = Field(default=None, index=True)
    payment_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    payment_method: str = Field(default="CASH", max_length=20)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    currency: str = Field(default="EGP", max_length=3)
    amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    status: SalesPaymentStatus = Field(
        default=SalesPaymentStatus.DRAFT,
        sa_column=Column(
            sa.Enum(SalesPaymentStatus, name="salespaymentstatus", schema="tenant"),
            nullable=False,
        ),
    )

    allocations: list["SalesPaymentAllocation"] = Relationship(
        back_populates="payment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )


class SalesPaymentAllocation(TenantBase, table=True):
    """
    Allocation of a SalesPayment against a posted SalesInvoice.
    """

    __tablename__ = "sales_payment_allocations"
    __table_args__ = ({"schema": "tenant"},)

    payment_id: UUID = Field(foreign_key="tenant.sales_payments.id", index=True)
    invoice_id: UUID = Field(foreign_key="tenant.sales_invoices.id", index=True)
    allocated_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )

    payment: Optional[SalesPayment] = Relationship(back_populates="allocations")
    invoice: Optional[SalesInvoice] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
    )
