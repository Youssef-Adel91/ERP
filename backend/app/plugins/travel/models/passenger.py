"""
app/plugins/travel/models/passenger.py — Structured Passenger Records

WHY THIS EXISTS:
The existing `passenger_manifest` in Case.data (JSONB) works for simple
read-only display but has no CRUD API — staff can't add a passenger, edit their
passport number, or link them to a VisaApplication without overwriting the
entire manifest blob. This model adds proper per-passenger records:

  ✅ Full CRUD (add/edit/delete individual passengers from a booking)
  ✅ Linkable to a VisaApplication (optional FK) — so the Visas screen can
     show "which visa belongs to which passenger"
  ✅ Works ALONGSIDE the existing JSONB manifest — does not replace it.
     The financials.py service continues to read from Case.data["passenger_manifest"]
     (unchanged). This table is the authoritative CRUD store; the JSONB
     manifest is kept as a legacy read/display cache.

DECOUPLING CONTRACT:
  ✅ FK to Case (booking) — CASCADE DELETE when booking is removed
  ✅ Optional FK to VisaApplication — SET NULL when visa is removed
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Index
from sqlmodel import Field

from app.core.db.base import TenantBase


class TravelPassenger(TenantBase, table=True):
    """
    A single passenger on a travel booking Case.
    Multiple passengers can belong to one Case (group bookings).
    """
    __tablename__ = "travel_passengers"
    __table_args__ = (
        Index("ix_travel_passengers_case", "case_id"),
        Index("ix_travel_passengers_visa", "visa_application_id"),
        {"schema": "tenant"},
    )

    case_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tenant.cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Optional link to a VisaApplication for this passenger.
    # SET NULL on visa deletion so the passenger record survives even if the
    # visa tracking entry is archived.
    visa_application_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("tenant.travel_visa_applications.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # Identity fields
    full_name: str = Field(max_length=255)
    full_name_ar: str | None = Field(default=None, max_length=255)

    # Travel document
    passport_number: str | None = Field(default=None, max_length=50)
    passport_expiry: date | None = Field(default=None)

    # Demographic
    date_of_birth: date | None = Field(default=None)
    nationality: str | None = Field(default=None, max_length=100)
    gender: str | None = Field(default=None, max_length=10)  # male / female

    # Booking role
    passenger_type: str = Field(
        default="adult",
        max_length=10,
        description="adult | child | infant",
    )

    # Soft delete — a passenger with a linked visa or financial record
    # should never be hard-deleted; set is_active=False instead.
    is_active: bool = Field(default=True, index=True)
