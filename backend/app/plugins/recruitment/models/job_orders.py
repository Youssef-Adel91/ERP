"""
app/plugins/recruitment/models/job_orders.py — Job Order Model

DECOUPLING CONTRACT:
  ✅ Imports only from app.core.db.base (TenantBase)
  ❌ Never imports from accounting, contacts, or cases core modules directly

A JobOrder is the foreign employer's demand ticket. Each open position
within a JobOrder is filled by associating a Case (candidate_deployment
type) with the order via the JobOrderCase join table.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field

from app.core.db.base import TenantBase


class JobOrderStatus(StrEnum):
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class JobOrder(TenantBase, table=True):
    """
    Represents a foreign employer's staffing demand:
      "We need 20 welders for Saudi Arabia."

    sponsor_id      → Contact.id (role: sponsor) who issued the order.
    required_profession → Must match candidate Case.data["profession"].
    target_count    → Total vacancies in this order.
    fulfilled_count → Populated by the matching service as candidates are attached.
    """

    __tablename__ = "recruitment_job_orders"
    __table_args__ = (
        Index("ix_job_orders_sponsor", "sponsor_id"),
        Index("ix_job_orders_status", "status"),
        Index("ix_job_orders_profession", "required_profession"),
        {"schema": "tenant"},
    )

    order_reference: str = Field(max_length=100, index=True)
    sponsor_id: UUID = Field(foreign_key="tenant.contacts.id", index=True)
    required_profession: str = Field(max_length=200)
    target_country: str = Field(max_length=100)
    target_count: int = Field(ge=1)
    fulfilled_count: int = Field(default=0)
    status: str = Field(default=JobOrderStatus.OPEN, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)


class JobOrderCase(TenantBase, table=True):
    """
    Join table: links a JobOrder to a candidate Case.
    One Case (one candidate) can only be attached to one JobOrder.
    """

    __tablename__ = "recruitment_job_order_cases"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_job_order_cases_case"),
        {"schema": "tenant"},
    )

    job_order_id: UUID = Field(foreign_key="tenant.recruitment_job_orders.id", index=True)
    case_id: UUID = Field(foreign_key="tenant.cases.id", index=True)
