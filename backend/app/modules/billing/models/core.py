"""
app.modules.billing.models.core — Billing Domain Models (Phase 8)
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, Numeric, JSON
from sqlmodel import Field, SQLModel


class PlanTier(str, enum.Enum):
    ENTRY = "ENTRY"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"


class SubscriptionState(str, enum.Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    PAID = "PAID"
    VOID = "VOID"
    UNCOLLECTIBLE = "UNCOLLECTIBLE"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Plan(SQLModel, table=True):
    """
    Available Subscription Plans.
    Schema: public (cross-tenant)
    """
    __tablename__ = "billing_plan"
    __table_args__ = {"schema": "public", "extend_existing": True}

    code: str = Field(primary_key=True, max_length=50)
    tier: PlanTier = Field(...)
    price_monthly: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(10, 2), nullable=False)
    )
    entitlements: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}")
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)}
    )


class Subscription(SQLModel, table=True):
    """
    A tenant's subscription to a Plan.
    Schema: public (cross-tenant)
    """
    __tablename__ = "billing_subscription"
    __table_args__ = {"schema": "public", "extend_existing": True}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID = Field(index=True, unique=True)
    
    plan_code: str = Field(foreign_key="public.billing_plan.code", index=True)
    state: SubscriptionState = Field(default=SubscriptionState.TRIALING)
    
    current_period_end: datetime = Field(...)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)}
    )


class SubscriptionInvoice(SQLModel, table=True):
    """
    An invoice generated for a subscription period.
    Schema: public (cross-tenant)
    """
    __tablename__ = "billing_subscription_invoice"
    __table_args__ = {"schema": "public", "extend_existing": True}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    subscription_id: UUID = Field(foreign_key="public.billing_subscription.id", index=True)
    
    amount: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False)
    )
    status: InvoiceStatus = Field(default=InvoiceStatus.OPEN)

    due_date: datetime = Field(...)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)}
    )


class PaymentAttempt(SQLModel, table=True):
    """
    A record of a payment attempt against a SubscriptionInvoice.
    Schema: public (cross-tenant)
    """
    __tablename__ = "billing_payment_attempt"
    __table_args__ = {"schema": "public", "extend_existing": True}

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    invoice_id: UUID = Field(foreign_key="public.billing_subscription_invoice.id", index=True)
    
    provider: str = Field(max_length=50)  # e.g., 'stripe', 'paymob'
    transaction_ref: str | None = Field(default=None, max_length=100)
    
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    error_message: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
