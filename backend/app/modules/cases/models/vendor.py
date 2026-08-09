"""
app.modules.cases.models.vendor — Vendor / Supplier Rate Card (Core)

Per SRS_Addendum_v1.1 §A.7 (Travel & Recruitment vertical detail):
  Travel: "ملف مورد: شركة طيران، فندق، مشغّل رحلات، شركة نقل - مع سجل
           أسعار سابقة وشروط إلغاء كل مورد"
  Recruitment: "ملف صاحب العمل/الكفيل بالخارج" (a lighter case — sponsors
           are modeled as Contacts with role="sponsor" already, per
           app.plugins.recruitment.bootstrap's CONTACT_ROLE_SCHEMAS, so
           this Vendor model is NOT for sponsors — it's for the B2B supply
           side: airlines, hotels, visa agencies, transport, tour
           operators — the counterparties a booking's `services[]` line
           items reference via `supplier_name`/`supplier_id` today as
           free text, with no structured cost lookup behind them.

Lives in Core (app.modules.cases), not the travel plugin, for the same
reason the Case Engine itself is Core: Recruitment ALSO deals with
external vendors (medical exam centers, visa processing agents) that need
the identical Vendor + rate-card shape — only the `service_type` values
differ, and those are free text (not a hardcoded enum) precisely so every
vertical can use its own vocabulary without a Core code change.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, Numeric, Text
from sqlmodel import Field

from app.core.db.base import TenantBase


class VendorType(StrEnum):
    AIRLINE = "AIRLINE"
    HOTEL = "HOTEL"
    VISA_AGENCY = "VISA_AGENCY"
    TRANSPORT = "TRANSPORT"
    TOUR_OPERATOR = "TOUR_OPERATOR"
    MEDICAL_CENTER = "MEDICAL_CENTER"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


class Vendor(TenantBase, table=True):
    """A B2B supplier a booking/case's services reference (airline, hotel, visa agency, ...)."""

    __tablename__ = "case_vendors"
    __table_args__ = (
        Index("ix_case_vendors_type", "vendor_type"),
        {"schema": "tenant"},
    )

    name: str = Field(max_length=255, index=True)
    name_ar: str | None = Field(default=None, max_length=255)
    vendor_type: str = Field(default=VendorType.OTHER, max_length=30, index=True)

    contact_person: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)

    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_active: bool = Field(default=True)


class VendorRateCard(TenantBase, table=True):
    """
    A negotiated buy price from a Vendor for a given service_type, with a
    validity window. `service_type` is free text (not an enum) — it should
    match whatever value a vertical's booking schema uses (e.g. Travel's
    "flight"/"hotel"/"visa"/... from app.plugins.travel.bootstrap).
    """

    __tablename__ = "case_vendor_rate_cards"
    __table_args__ = (
        Index("ix_vendor_rate_cards_vendor", "vendor_id"),
        Index("ix_vendor_rate_cards_service_type", "service_type"),
        {"schema": "tenant"},
    )

    vendor_id: UUID = Field(foreign_key="tenant.case_vendors.id", index=True)
    service_type: str = Field(max_length=100, index=True)
    description: str | None = Field(default=None, max_length=500)

    buy_price: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    currency: str = Field(default="EGP", max_length=3)

    valid_from: date = Field(default_factory=lambda: datetime.now(UTC).date())
    valid_until: date | None = Field(default=None)

    cancellation_policy: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_active: bool = Field(default=True)
