"""
app/modules/purchasing/models/payments.py — Supplier Payments & Payment Allocations

Defines:
  1. SupplierPayment (inherits DocumentLifecycleMixin & TenantBase)
  2. PaymentAllocation (links SupplierPayment to VendorBill)
  3. SupplierPaymentStatus enum
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, Date, Numeric, String
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin, DocumentState
from app.modules.purchasing.models.billing import VendorBill


class SupplierPaymentStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class SupplierPayment(DocumentLifecycleMixin, TenantBase, table=True):
    """
    Supplier Payment document representing cash/bank payments to suppliers,
    with automatic FX gain/loss realization against allocated vendor bills.
    """

    __tablename__ = "supplier_payments"
    __table_args__ = ({"schema": "tenant"},)

    payment_number: str = Field(max_length=50, index=True, unique=True)
    supplier_id: UUID = Field(index=True)
    treasury_id: UUID = Field(index=True)
    payment_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    currency: str = Field(default="EGP", max_length=3)
    fx_rate: Decimal = Field(
        default=Decimal("1.000000"),
        sa_column=Column(Numeric(18, 6), nullable=False),
    )
    amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    fx_gain_loss_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    status: SupplierPaymentStatus = Field(
        default=SupplierPaymentStatus.DRAFT,
        sa_column=Column(sa.Enum(SupplierPaymentStatus), nullable=False),
    )

    allocations: list["PaymentAllocation"] = Relationship(
        back_populates="payment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PaymentAllocation(TenantBase, table=True):
    """
    Allocation of a SupplierPayment against a posted VendorBill.
    """

    __tablename__ = "payment_allocations"
    __table_args__ = ({"schema": "tenant"},)

    payment_id: UUID = Field(foreign_key="tenant.supplier_payments.id", index=True)
    bill_id: UUID = Field(foreign_key="tenant.vendor_bills.id", index=True)
    allocated_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )

    payment: Optional[SupplierPayment] = Relationship(back_populates="allocations")
    bill: Optional[VendorBill] = Relationship()
