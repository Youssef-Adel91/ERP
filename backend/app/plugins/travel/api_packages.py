"""
app/plugins/travel/api_packages.py — Travel Package Catalog + Itinerary API

Endpoints for managing the reusable package catalog (TravelPackage,
TravelItineraryDay, TravelPackageComponent) and for converting a package
into a real booking Case. See app/plugins/travel/models/package.py for the
full rationale.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.vendor import Vendor
from app.modules.cases.services.engine import create_case
from app.plugins.travel.bootstrap import bootstrap_travel_case_type
from app.plugins.travel.models.package import (
    TravelItineraryDay,
    TravelPackage,
    TravelPackageComponent,
    component_to_booking_service,
)

router = APIRouter(prefix="/travel/packages", tags=["Travel Plugin — Packages"])
components_router = APIRouter(prefix="/travel/components", tags=["Travel Plugin — Packages"])
itinerary_router = APIRouter(prefix="/travel/itinerary-days", tags=["Travel Plugin — Packages"])


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class ItineraryDayIn(BaseModel):
    day_number: int = PydanticField(ge=1)
    title_ar: str
    title_en: str | None = None
    description_ar: str | None = None
    description_en: str | None = None
    meals_included: list[str] = []


class ItineraryDayOut(ItineraryDayIn):
    id: UUID
    package_id: UUID

    class Config:
        from_attributes = True


class ComponentIn(BaseModel):
    day_number: int | None = None
    component_type: str = "other"
    vendor_id: UUID | None = None
    description: str
    net_cost: Decimal = Decimal("0")
    sell_price: Decimal = Decimal("0")
    currency: str = "EGP"
    quantity: int = PydanticField(default=1, ge=1)
    sort_order: int = 0


class ComponentOut(ComponentIn):
    id: UUID
    package_id: UUID
    vendor_name: str | None = None

    class Config:
        from_attributes = True


class PackageIn(BaseModel):
    name_ar: str
    name_en: str | None = None
    destination: str
    category: str = "other"
    duration_days: int = PydanticField(default=1, ge=1)
    duration_nights: int = PydanticField(default=0, ge=0)
    description_ar: str | None = None
    description_en: str | None = None
    currency: str = "EGP"
    min_pax: int = PydanticField(default=1, ge=1)
    max_pax: int | None = None
    cover_image_url: str | None = None
    inclusions: list[str] = []
    exclusions: list[str] = []
    is_active: bool = True
    # Optional nested create — lets the frontend build a package + full
    # itinerary + components in a single request instead of N+1 calls.
    itinerary_days: list[ItineraryDayIn] = []
    components: list[ComponentIn] = []


class PackagePatchIn(BaseModel):
    name_ar: str | None = None
    name_en: str | None = None
    destination: str | None = None
    category: str | None = None
    duration_days: int | None = None
    duration_nights: int | None = None
    description_ar: str | None = None
    description_en: str | None = None
    currency: str | None = None
    min_pax: int | None = None
    max_pax: int | None = None
    cover_image_url: str | None = None
    inclusions: list[str] | None = None
    exclusions: list[str] | None = None
    is_active: bool | None = None


class PackageOut(BaseModel):
    id: UUID
    name_ar: str
    name_en: str | None
    destination: str
    category: str
    duration_days: int
    duration_nights: int
    description_ar: str | None
    description_en: str | None
    base_price: Decimal
    base_cost: Decimal
    currency: str
    min_pax: int
    max_pax: int | None
    cover_image_url: str | None
    inclusions: list[str]
    exclusions: list[str]
    is_active: bool

    class Config:
        from_attributes = True


class PackageDetailOut(PackageOut):
    itinerary_days: list[ItineraryDayOut] = []
    components: list[ComponentOut] = []


class BookFromPackageIn(BaseModel):
    customer_name: str
    customer_name_ar: str | None = None
    origin: str | None = None
    travel_date_requested: date
    return_date_requested: date | None = None
    group_size: int | None = None  # defaults to package.min_pax
    notes: str | None = None
    contacts: list[dict[str, Any]] = []  # [{contact_id, role, meta}]


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _recompute_package_totals(session: AsyncSession, package_id: UUID) -> None:
    """Recomputes TravelPackage.base_price/base_cost from its components' sums."""
    result = await session.execute(
        select(TravelPackageComponent).where(TravelPackageComponent.package_id == package_id)
    )
    components = result.scalars().all()
    package = await session.get(TravelPackage, package_id)
    if not package:
        return
    package.base_cost = sum((c.net_cost * c.quantity for c in components), Decimal("0"))
    package.base_price = sum((c.sell_price * c.quantity for c in components), Decimal("0"))
    session.add(package)


async def _vendor_names(session: AsyncSession, vendor_ids: list[UUID]) -> dict[UUID, str]:
    if not vendor_ids:
        return {}
    result = await session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))
    return {v.id: v.name_ar or v.name for v in result.scalars().all()}


async def _load_package_detail(session: AsyncSession, package: TravelPackage) -> PackageDetailOut:
    days_result = await session.execute(
        select(TravelItineraryDay)
        .where(TravelItineraryDay.package_id == package.id)
        .order_by(TravelItineraryDay.day_number)
    )
    days = days_result.scalars().all()

    comps_result = await session.execute(
        select(TravelPackageComponent)
        .where(TravelPackageComponent.package_id == package.id)
        .order_by(TravelPackageComponent.sort_order, TravelPackageComponent.day_number)
    )
    comps = comps_result.scalars().all()
    vendor_names = await _vendor_names(session, [c.vendor_id for c in comps if c.vendor_id])

    return PackageDetailOut(
        **PackageOut.model_validate(package).model_dump(),
        itinerary_days=[ItineraryDayOut.model_validate(d) for d in days],
        components=[
            ComponentOut(**ComponentOut.model_validate(c).model_dump(exclude={"vendor_name"}), vendor_name=vendor_names.get(c.vendor_id))
            for c in comps
        ],
    )


# ── Package CRUD ─────────────────────────────────────────────────────────────


@router.get("", response_model=list[PackageOut])
async def list_packages(
    is_active: bool | None = None,
    destination: str | None = None,
    category: str | None = None,
    session: AsyncSession = Depends(get_tenant_db),
):
    q = select(TravelPackage)
    if is_active is not None:
        q = q.where(TravelPackage.is_active == is_active)
    if destination:
        q = q.where(TravelPackage.destination.ilike(f"%{destination}%"))
    if category:
        q = q.where(TravelPackage.category == category)
    q = q.order_by(TravelPackage.name_ar)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=PackageDetailOut, status_code=status.HTTP_201_CREATED)
async def create_package(body: PackageIn, session: AsyncSession = Depends(get_tenant_db)):
    data = body.model_dump(exclude={"itinerary_days", "components"})
    package = TravelPackage(**data)
    session.add(package)
    await session.flush()

    for day in body.itinerary_days:
        session.add(TravelItineraryDay(package_id=package.id, **day.model_dump()))
    for comp in body.components:
        session.add(TravelPackageComponent(package_id=package.id, **comp.model_dump()))
    await session.flush()

    await _recompute_package_totals(session, package.id)
    await session.commit()
    # Do NOT use session.refresh(package) after commit — the schema_translate_map
    # can be lost on the refreshed connection, causing "tenant.travel_packages does
    # not exist" errors.  Use session.get() which routes through the same session.
    reloaded = await session.get(TravelPackage, package.id)
    return await _load_package_detail(session, reloaded)  # type: ignore[arg-type]


@router.get("/{package_id}", response_model=PackageDetailOut)
async def get_package(package_id: UUID, session: AsyncSession = Depends(get_tenant_db)):
    package = await session.get(TravelPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="الباقة غير موجودة.")
    return await _load_package_detail(session, package)


@router.patch("/{package_id}", response_model=PackageDetailOut)
async def update_package(package_id: UUID, body: PackagePatchIn, session: AsyncSession = Depends(get_tenant_db)):
    package = await session.get(TravelPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="الباقة غير موجودة.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(package, field, value)
    session.add(package)
    await session.commit()
    reloaded = await session.get(TravelPackage, package_id)
    return await _load_package_detail(session, reloaded)  # type: ignore[arg-type]


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(package_id: UUID, session: AsyncSession = Depends(get_tenant_db)):
    package = await session.get(TravelPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="الباقة غير موجودة.")
    await session.delete(package)
    await session.commit()


# ── Itinerary Days ───────────────────────────────────────────────────────────


@router.post("/{package_id}/itinerary-days", response_model=ItineraryDayOut, status_code=status.HTTP_201_CREATED)
async def add_itinerary_day(package_id: UUID, body: ItineraryDayIn, session: AsyncSession = Depends(get_tenant_db)):
    package = await session.get(TravelPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="الباقة غير موجودة.")
    day = TravelItineraryDay(package_id=package_id, **body.model_dump())
    session.add(day)
    await session.commit()
    await session.refresh(day)
    return day


@itinerary_router.patch("/{day_id}", response_model=ItineraryDayOut)
async def update_itinerary_day(day_id: UUID, body: ItineraryDayIn, session: AsyncSession = Depends(get_tenant_db)):
    day = await session.get(TravelItineraryDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="يوم البرنامج غير موجود.")
    for field, value in body.model_dump().items():
        setattr(day, field, value)
    session.add(day)
    await session.commit()
    await session.refresh(day)
    return day


@itinerary_router.delete("/{day_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_itinerary_day(day_id: UUID, session: AsyncSession = Depends(get_tenant_db)):
    day = await session.get(TravelItineraryDay, day_id)
    if not day:
        raise HTTPException(status_code=404, detail="يوم البرنامج غير موجود.")
    await session.delete(day)
    await session.commit()


# ── Components ───────────────────────────────────────────────────────────────


@router.post("/{package_id}/components", response_model=ComponentOut, status_code=status.HTTP_201_CREATED)
async def add_component(package_id: UUID, body: ComponentIn, session: AsyncSession = Depends(get_tenant_db)):
    package = await session.get(TravelPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="الباقة غير موجودة.")
    component = TravelPackageComponent(package_id=package_id, **body.model_dump())
    session.add(component)
    await session.flush()
    await _recompute_package_totals(session, package_id)
    await session.commit()
    await session.refresh(component)
    vendor_names = await _vendor_names(session, [component.vendor_id] if component.vendor_id else [])
    return ComponentOut(**ComponentOut.model_validate(component).model_dump(exclude={"vendor_name"}), vendor_name=vendor_names.get(component.vendor_id))


@components_router.patch("/{component_id}", response_model=ComponentOut)
async def update_component(component_id: UUID, body: ComponentIn, session: AsyncSession = Depends(get_tenant_db)):
    component = await session.get(TravelPackageComponent, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="العنصر غير موجود.")
    for field, value in body.model_dump().items():
        setattr(component, field, value)
    session.add(component)
    await session.flush()
    await _recompute_package_totals(session, component.package_id)
    await session.commit()
    await session.refresh(component)
    vendor_names = await _vendor_names(session, [component.vendor_id] if component.vendor_id else [])
    return ComponentOut(**ComponentOut.model_validate(component).model_dump(exclude={"vendor_name"}), vendor_name=vendor_names.get(component.vendor_id))


@components_router.delete("/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_component(component_id: UUID, session: AsyncSession = Depends(get_tenant_db)):
    component = await session.get(TravelPackageComponent, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="العنصر غير موجود.")
    package_id = component.package_id
    await session.delete(component)
    await session.flush()
    await _recompute_package_totals(session, package_id)
    await session.commit()


# ── Create Booking From Package ───────────────────────────────────────────────


@router.post("/{package_id}/book", status_code=status.HTTP_201_CREATED)
async def create_booking_from_package(
    package_id: UUID,
    body: BookFromPackageIn,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Converts a TravelPackage into a real travel_booking Case: copies every
    component into `data.services[]` (buy/sell prices frozen at this
    moment — later edits to the package template never change an
    already-sold booking) and stores a lightweight `package_snapshot` so
    the booking always shows which package it came from, even if the
    template is later edited or deleted.
    """
    package = await session.get(TravelPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="الباقة غير موجودة.")

    comps_result = await session.execute(
        select(TravelPackageComponent)
        .where(TravelPackageComponent.package_id == package_id)
        .order_by(TravelPackageComponent.sort_order, TravelPackageComponent.day_number)
    )
    comps = comps_result.scalars().all()
    vendor_names = await _vendor_names(session, [c.vendor_id for c in comps if c.vendor_id])

    services = [
        component_to_booking_service(c.model_dump(), vendor_name=vendor_names.get(c.vendor_id))
        for c in comps
    ]
    total_buy = sum((c.net_cost * c.quantity for c in comps), Decimal("0"))
    total_sell = sum((c.sell_price * c.quantity for c in comps), Decimal("0"))

    case_type = await bootstrap_travel_case_type(session)

    case_data: dict[str, Any] = {
        "customer_name": body.customer_name,
        "customer_name_ar": body.customer_name_ar,
        "destination": package.destination,
        "origin": body.origin,
        "travel_date_requested": body.travel_date_requested.isoformat(),
        "return_date_requested": body.return_date_requested.isoformat() if body.return_date_requested else None,
        "group_size": body.group_size or package.min_pax,
        "trip_type": "package",
        "services": services,
        "currency": package.currency,
        "notes": body.notes,
        "package_snapshot": {
            "package_id": str(package.id),
            "name_ar": package.name_ar,
            "duration_days": package.duration_days,
            "duration_nights": package.duration_nights,
            "buy_price": float(total_buy),
            "sell_price": float(total_sell),
        },
    }

    tenant_id: str = request.state.tenant_id
    user_id: str | None = getattr(request.state, "current_user_id", None)

    case = await create_case(
        session,
        tenant_id=tenant_id,
        case_type_id=case_type.id,
        title=f"{package.name_ar} — {body.customer_name}",
        start_date=body.travel_date_requested,
        end_date=body.return_date_requested,
        data=case_data,
        contacts=body.contacts,
        created_by=UUID(user_id) if user_id else None,
    )
    await session.commit()
    await session.refresh(case)
    return case
