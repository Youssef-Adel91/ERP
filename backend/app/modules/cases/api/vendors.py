"""
app/modules/cases/api/vendors.py — Vendor & Rate Card API (Core)

Route ordering note (same issue as api/alerts.py): the literal path
`/cases/vendors/rates` is declared BEFORE `/cases/vendors/{vendor_id}` in
this router, and this whole router is mounted in app.modules.cases.router
BEFORE the generic cases_router (whose `/cases/{id}` would otherwise
swallow `/cases/vendors`). Both orderings matter — within this file and
across the module's router.py.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.vendor import Vendor, VendorRateCard, VendorType
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/cases/vendors", tags=["Case Engine — Vendors"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class VendorIn(BaseModel):
    name: str
    name_ar: str | None = None
    vendor_type: VendorType = VendorType.OTHER
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    is_active: bool = True


class RateCardIn(BaseModel):
    service_type: str
    description: str | None = None
    buy_price: Decimal
    currency: str = "EGP"
    valid_from: date | None = None
    valid_until: date | None = None
    cancellation_policy: str | None = None
    is_active: bool = True


class RateLookupOut(BaseModel):
    id: UUID
    vendor_id: UUID
    vendor_name: str
    service_type: str
    description: str | None
    buy_price: Decimal
    currency: str
    valid_from: date
    valid_until: date | None
    cancellation_policy: str | None


# ── Rate lookup (MUST be declared before /{vendor_id}) ────────────────────────


@router.get("/rates", response_model=list[RateLookupOut])
async def lookup_rates(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    service_type: str | None = Query(default=None),
):
    """
    Cross-vendor rate lookup for a service type — this is what the Generic
    Case Engine's dynamic form would call (client-side, once wired) when a
    "services[]" row's service_type is picked, to suggest/pre-fill the
    internal buy_price. Only returns currently-valid, active rate cards
    (valid_from <= today <= valid_until-or-open-ended), cheapest first.
    """
    today = datetime.now(UTC).date()
    q = (
        select(VendorRateCard, Vendor)
        .join(Vendor, VendorRateCard.vendor_id == Vendor.id)
        .where(
            VendorRateCard.is_active == True,  # noqa: E712
            Vendor.is_active == True,  # noqa: E712
            VendorRateCard.valid_from <= today,
        )
    )
    if service_type:
        q = q.where(VendorRateCard.service_type == service_type)

    rows = (await session.execute(q)).all()
    results = [
        RateLookupOut(
            id=rc.id,
            vendor_id=rc.vendor_id,
            vendor_name=vendor.name,
            service_type=rc.service_type,
            description=rc.description,
            buy_price=rc.buy_price,
            currency=rc.currency,
            valid_from=rc.valid_from,
            valid_until=rc.valid_until,
            cancellation_policy=rc.cancellation_policy,
        )
        for rc, vendor in rows
        if rc.valid_until is None or rc.valid_until >= today
    ]
    results.sort(key=lambda r: r.buy_price)
    return results


# ── Vendor CRUD ────────────────────────────────────────────────────────────────


@router.post("", response_model=Vendor, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    data: VendorIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    vendor = Vendor(**data.model_dump(), created_by=current_user.id)
    session.add(vendor)
    await session.commit()
    await session.refresh(vendor)
    return vendor


@router.get("", response_model=list[Vendor])
async def list_vendors(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    vendor_type: VendorType | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    q = select(Vendor)
    if vendor_type:
        q = q.where(Vendor.vendor_type == vendor_type)
    if is_active is not None:
        q = q.where(Vendor.is_active == is_active)
    result = await session.execute(q.order_by(Vendor.name))
    return result.scalars().all()


@router.get("/{vendor_id}", response_model=Vendor)
async def get_vendor(
    vendor_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    vendor = await session.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")
    return vendor


@router.put("/{vendor_id}", response_model=Vendor)
async def update_vendor(
    vendor_id: UUID,
    data: VendorIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    vendor = await session.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")
    for field, value in data.model_dump().items():
        setattr(vendor, field, value)
    session.add(vendor)
    await session.commit()
    await session.refresh(vendor)
    return vendor


# ── Rate Cards (nested under a vendor) ─────────────────────────────────────────


@router.post("/{vendor_id}/rates", response_model=VendorRateCard, status_code=status.HTTP_201_CREATED)
async def create_rate_card(
    vendor_id: UUID,
    data: RateCardIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    vendor = await session.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    payload = data.model_dump()
    if payload.get("valid_from") is None:
        payload["valid_from"] = datetime.now(UTC).date()

    rate_card = VendorRateCard(vendor_id=vendor_id, **payload, created_by=current_user.id)
    session.add(rate_card)
    await session.commit()
    await session.refresh(rate_card)
    return rate_card


@router.get("/{vendor_id}/rates", response_model=list[VendorRateCard])
async def list_vendor_rate_cards(
    vendor_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    result = await session.execute(
        select(VendorRateCard).where(VendorRateCard.vendor_id == vendor_id).order_by(VendorRateCard.valid_from.desc())
    )
    return result.scalars().all()


@router.put("/{vendor_id}/rates/{rate_id}", response_model=VendorRateCard)
async def update_rate_card(
    vendor_id: UUID,
    rate_id: UUID,
    data: RateCardIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    rate_card = await session.get(VendorRateCard, rate_id)
    if not rate_card or rate_card.vendor_id != vendor_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate card not found.")

    payload = data.model_dump()
    if payload.get("valid_from") is None:
        payload["valid_from"] = rate_card.valid_from

    for field, value in payload.items():
        setattr(rate_card, field, value)
    session.add(rate_card)
    await session.commit()
    await session.refresh(rate_card)
    return rate_card
