"""
app/plugins/travel/models/visa.py — Visa Application Tracking

WHY THIS EXISTS:
Before this, a visa was just one more free-text line in a booking Case's
`services[]` array (service_type="visa") — no sub-status, no submission/
decision dates, no way to see "which visas are pending across ALL active
bookings" without opening every Case individually. Visa processing is
genuinely its own multi-step pipeline (documents → submission → decision)
independent of the booking's own stage (a booking can be "confirmed" while
its visa is still "submitted"), so it needs its own status machine.

A VisaApplication always belongs to a booking Case (case_id) and a named
passenger (passenger_name/passport_number — copied at creation time from
the booking's passenger_manifest rather than FK'd to a Contact, because
most travel passengers are manifest entries, not full Contact records).

DECOUPLING CONTRACT:
  ✅ FKs to Case (booking) and optionally Vendor (the visa processing agency)
  ✅ Pure tracking — does not itself post to GL. cost/fee are surfaced to
     the booking's financials the same way any other service line is; a
     future improvement could feed VisaApplication.visa_expiry_date into
     app.modules.cases.services.alerts' expiration scanner alongside
     CaseContact.meta, but that's explicitly out of scope for now (noted
     in VERTICAL_SYSTEMS_ROADMAP.md).
  ❌ Never imports from app.modules.accounting directly
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Index, Numeric, Text
from sqlmodel import Field

from app.core.db.base import TenantBase


class VisaStatus(StrEnum):
    NOT_STARTED = "not_started"
    DOCUMENTS_COLLECTED = "documents_collected"
    SUBMITTED = "submitted"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"


# Status transitions considered forward progress (used by the API to reject
# nonsensical jumps like RECEIVED -> DOCUMENTS_COLLECTED without an explicit
# override flag). Kept permissive on purpose — rejection/resubmission is a
# real workflow (REJECTED -> DOCUMENTS_COLLECTED is valid), so this is a
# soft ordering hint, not a hard state machine like the Case Engine's.
VISA_STATUS_ORDER: dict[str, int] = {
    VisaStatus.NOT_STARTED: 0,
    VisaStatus.DOCUMENTS_COLLECTED: 1,
    VisaStatus.SUBMITTED: 2,
    VisaStatus.INTERVIEW_SCHEDULED: 3,
    VisaStatus.APPROVED: 4,
    VisaStatus.RECEIVED: 5,
    VisaStatus.REJECTED: 4,  # can occur after submission/interview
}


class VisaApplication(TenantBase, table=True):
    __tablename__ = "travel_visa_applications"
    __table_args__ = (
        Index("ix_travel_visa_applications_case", "case_id"),
        Index("ix_travel_visa_applications_status", "status"),
        Index("ix_travel_visa_applications_vendor", "vendor_id"),
        {"schema": "tenant"},
    )

    case_id: UUID = Field(
        sa_column=Column(ForeignKey("tenant.cases.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    passenger_name: str = Field(max_length=255)
    passport_number: str | None = Field(default=None, max_length=50)

    destination_country: str = Field(max_length=100)
    visa_type: str = Field(default="tourist", max_length=30)  # tourist/business/work/transit/other
    status: str = Field(default=VisaStatus.NOT_STARTED, max_length=30, index=True)

    vendor_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("tenant.case_vendors.id", ondelete="SET NULL"), nullable=True, index=True),
    )

    submitted_date: date | None = Field(default=None)
    expected_decision_date: date | None = Field(default=None)
    decision_date: date | None = Field(default=None)

    visa_number: str | None = Field(default=None, max_length=100)
    visa_issue_date: date | None = Field(default=None)
    visa_expiry_date: date | None = Field(default=None)

    # Buy/sell shape, consistent with TravelPackageComponent and the
    # booking's own service lines — what we pay the visa agency vs. what we
    # charge the customer for handling it.
    cost: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2), nullable=False))
    fee_charged: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2), nullable=False))
    currency: str = Field(default="EGP", max_length=3)

    rejection_reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
