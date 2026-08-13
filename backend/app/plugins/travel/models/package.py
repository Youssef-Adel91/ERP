"""
app/plugins/travel/models/package.py — Reusable Travel Package Catalog

WHY THIS EXISTS:
Before this, every travel booking was built entirely from scratch inside a
Case's `data` JSONB (see app.plugins.travel.bootstrap's TRAVEL_BOOKING_STAGES
"services"/"passenger_manifest" schema) — there was no way to define a
sellable package ONCE (e.g. "3 nights Sharm — Diving Package") and reuse it
across many bookings. Agencies that sell the same handful of packages
repeatedly need a catalog, not a blank form every time.

This module adds that catalog layer ON TOP of the existing Case Engine — it
does NOT replace it. A TravelPackage is a template: fixed itinerary days +
priced components (service_type, net_cost, sell_price, optional vendor).
Selling a package creates a normal travel_booking Case, with `services[]`
and a `package_snapshot` pre-filled by copying the package's components at
that moment (see app.plugins.travel.api_packages.create_booking_from_package)
— so later edits to the package template never retroactively change an
already-sold booking's committed price.

DECOUPLING CONTRACT (same convention as the rest of this plugin):
  ✅ References app.modules.cases.models.vendor.Vendor by FK (optional)
  ✅ service_type values match the exact vocabulary already used in
     TRAVEL_BOOKING_STAGES["inquiry"]["services"][*]["service_type"] enum
     (flight/hotel/transfer/visa/travel_insurance/excursion/car_rental/other)
     — this is what lets a package component convert 1:1 into a booking
     service line with zero translation.
  ❌ Never imports from app.modules.accounting directly
"""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, ForeignKey, Index, Numeric, Text
from sqlmodel import Field

from app.core.db.base import TenantBase


class TravelServiceType(StrEnum):
    """
    Mirrors the free-text `service_type` enum already used in
    app.plugins.travel.bootstrap.TRAVEL_BOOKING_STAGES's "services" schema.
    Kept as an explicit Python enum here (unlike the JSON-schema-only
    version in bootstrap.py) so package components get real validation.
    """
    FLIGHT = "flight"
    HOTEL = "hotel"
    TRANSFER = "transfer"
    VISA = "visa"
    TRAVEL_INSURANCE = "travel_insurance"
    EXCURSION = "excursion"
    CAR_RENTAL = "car_rental"
    OTHER = "other"


class TravelPackageCategory(StrEnum):
    FAMILY = "family"
    HONEYMOON = "honeymoon"
    RELIGIOUS = "religious"
    ADVENTURE = "adventure"
    CORPORATE = "corporate"
    GROUP = "group"
    BEACH = "beach"
    CITY_BREAK = "city_break"
    OTHER = "other"


class TravelPackage(TenantBase, table=True):
    """
    A reusable, sellable travel package template — e.g. "4 Days / 3 Nights
    Sharm El Sheikh — Diving Package". Priced components and itinerary days
    live in TravelPackageComponent / TravelItineraryDay (child tables).
    """
    __tablename__ = "travel_packages"
    __table_args__ = (
        Index("ix_travel_packages_destination", "destination"),
        Index("ix_travel_packages_category", "category"),
        Index("ix_travel_packages_active", "is_active"),
        {"schema": "tenant"},
    )

    name_ar: str = Field(max_length=255, index=True)
    name_en: str | None = Field(default=None, max_length=255)
    destination: str = Field(max_length=255)
    category: str = Field(default=TravelPackageCategory.OTHER, max_length=30)

    duration_days: int = Field(default=1, ge=1)
    duration_nights: int = Field(default=0, ge=0)

    description_ar: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    description_en: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    # Headline price shown in the catalog — the authoritative total is the
    # sum of TravelPackageComponent.sell_price, this is a denormalized cache
    # for list views, refreshed whenever components are saved (see
    # api_packages.py's _recompute_package_totals).
    base_price: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2), nullable=False))
    base_cost: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2), nullable=False))
    currency: str = Field(default="EGP", max_length=3)

    min_pax: int = Field(default=1, ge=1)
    max_pax: int | None = Field(default=None)

    cover_image_url: str | None = Field(default=None, max_length=1000)
    inclusions: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    exclusions: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    is_active: bool = Field(default=True, index=True)


class TravelItineraryDay(TenantBase, table=True):
    """One day of a package's day-by-day itinerary (Day 1, Day 2, ...)."""
    __tablename__ = "travel_itinerary_days"
    __table_args__ = (
        Index("ix_travel_itinerary_days_package", "package_id"),
        {"schema": "tenant"},
    )

    package_id: UUID = Field(
        sa_column=Column(ForeignKey("tenant.travel_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    day_number: int = Field(ge=1)
    title_ar: str = Field(max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    description_ar: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    description_en: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    meals_included: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class TravelPackageComponent(TenantBase, table=True):
    """
    A single priced line item inside a package — a hotel stay, a transfer,
    an excursion, etc. `net_cost` is what the agency pays the vendor;
    `sell_price` is what the agency charges the customer. The difference is
    the margin — same buy/sell shape as the booking-level `services[]`
    array in Case.data, deliberately, so converting a package into a real
    booking (create_booking_from_package) is a straight field copy.
    """
    __tablename__ = "travel_package_components"
    __table_args__ = (
        Index("ix_travel_package_components_package", "package_id"),
        Index("ix_travel_package_components_vendor", "vendor_id"),
        {"schema": "tenant"},
    )

    package_id: UUID = Field(
        sa_column=Column(ForeignKey("tenant.travel_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    day_number: int | None = Field(default=None, description="Which itinerary day this component belongs to, if any.")
    component_type: str = Field(default=TravelServiceType.OTHER, max_length=30)
    vendor_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("tenant.case_vendors.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    description: str = Field(max_length=500)

    net_cost: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2), nullable=False))
    sell_price: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(18, 2), nullable=False))
    currency: str = Field(default="EGP", max_length=3)
    quantity: int = Field(default=1, ge=1)

    sort_order: int = Field(default=0)


def component_to_booking_service(component: dict[str, Any], vendor_name: str | None = None) -> dict[str, Any]:
    """
    Converts one TravelPackageComponent (as a dict) into a booking-Case
    "services[]" line item matching the shape TRAVEL_BOOKING_STAGES expects.
    Shared helper so api_packages.py's create-booking endpoint and any
    future caller produce byte-identical service line shapes.
    """
    return {
        "service_type": component.get("component_type", TravelServiceType.OTHER),
        "supplier_id": str(component["vendor_id"]) if component.get("vendor_id") else None,
        "supplier_name": vendor_name,
        "description": component.get("description"),
        "buy_price": float(component.get("net_cost", 0)),
        "sell_price": float(component.get("sell_price", 0)),
        "currency": component.get("currency", "EGP"),
        "quantity": component.get("quantity", 1),
    }
