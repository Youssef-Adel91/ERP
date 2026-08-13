"""
app/plugins/travel/api_visas.py — Visa Application Tracking API

See app/plugins/travel/models/visa.py for the full rationale. Endpoints
live under both /travel/visas (global list — "which visas are pending
across all bookings") and /travel/cases/{case_id}/visas (scoped to one
booking), since both views are genuinely useful for an agency.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case
from app.modules.cases.models.vendor import Vendor
from app.plugins.travel.models.visa import VISA_STATUS_ORDER, VisaApplication, VisaStatus

router = APIRouter(prefix="/travel", tags=["Travel Plugin — Visas"])


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class VisaCreateIn(BaseModel):
    passenger_name: str
    passport_number: str | None = None
    destination_country: str
    visa_type: str = "tourist"
    vendor_id: UUID | None = None
    expected_decision_date: date | None = None
    cost: Decimal = Decimal("0")
    fee_charged: Decimal = Decimal("0")
    currency: str = "EGP"
    notes: str | None = None


class VisaPatchIn(BaseModel):
    passenger_name: str | None = None
    passport_number: str | None = None
    destination_country: str | None = None
    visa_type: str | None = None
    vendor_id: UUID | None = None
    submitted_date: date | None = None
    expected_decision_date: date | None = None
    decision_date: date | None = None
    visa_number: str | None = None
    visa_issue_date: date | None = None
    visa_expiry_date: date | None = None
    cost: Decimal | None = None
    fee_charged: Decimal | None = None
    rejection_reason: str | None = None
    notes: str | None = None


class VisaStatusTransitionIn(BaseModel):
    status: VisaStatus
    rejection_reason: str | None = None
    # Set True to allow a status change that looks like backward movement
    # without it being a legitimate resubmission (REJECTED -> DOCUMENTS_COLLECTED
    # is always allowed; anything else out-of-order needs this flag).
    force: bool = False


class VisaOut(BaseModel):
    id: UUID
    case_id: UUID
    passenger_name: str
    passport_number: str | None
    destination_country: str
    visa_type: str
    status: str
    vendor_id: UUID | None
    vendor_name: str | None = None
    submitted_date: date | None
    expected_decision_date: date | None
    decision_date: date | None
    visa_number: str | None
    visa_issue_date: date | None
    visa_expiry_date: date | None
    cost: Decimal
    fee_charged: Decimal
    currency: str
    rejection_reason: str | None
    notes: str | None
    booking_title: str | None = None

    class Config:
        from_attributes = True


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _to_out(session: AsyncSession, visa: VisaApplication) -> VisaOut:
    vendor_name = None
    if visa.vendor_id:
        vendor = await session.get(Vendor, visa.vendor_id)
        vendor_name = vendor.name_ar or vendor.name if vendor else None
    case = await session.get(Case, visa.case_id)
    return VisaOut(
        **VisaOut.model_validate(visa).model_dump(exclude={"vendor_name", "booking_title"}),
        vendor_name=vendor_name,
        booking_title=case.title if case else None,
    )


# ── Global list ──────────────────────────────────────────────────────────────


@router.get("/visas", response_model=list[VisaOut])
async def list_visas(
    status_filter: str | None = None,
    destination_country: str | None = None,
    session: AsyncSession = Depends(get_tenant_db),
):
    q = select(VisaApplication)
    if status_filter:
        q = q.where(VisaApplication.status == status_filter)
    if destination_country:
        q = q.where(VisaApplication.destination_country.ilike(f"%{destination_country}%"))
    q = q.order_by(VisaApplication.expected_decision_date.nulls_last())
    result = await session.execute(q)
    visas = result.scalars().all()
    return [await _to_out(session, v) for v in visas]


# ── Scoped to a booking ──────────────────────────────────────────────────────


@router.get("/cases/{case_id}/visas", response_model=list[VisaOut])
async def list_case_visas(case_id: UUID, session: AsyncSession = Depends(get_tenant_db)):
    result = await session.execute(
        select(VisaApplication).where(VisaApplication.case_id == case_id)
    )
    visas = result.scalars().all()
    return [await _to_out(session, v) for v in visas]


@router.post("/cases/{case_id}/visas", response_model=VisaOut, status_code=status.HTTP_201_CREATED)
async def create_visa(case_id: UUID, body: VisaCreateIn, session: AsyncSession = Depends(get_tenant_db)):
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="الحجز غير موجود.")
    visa = VisaApplication(case_id=case_id, **body.model_dump())
    session.add(visa)
    await session.commit()
    await session.refresh(visa)
    return await _to_out(session, visa)


@router.patch("/visas/{visa_id}", response_model=VisaOut)
async def update_visa(visa_id: UUID, body: VisaPatchIn, session: AsyncSession = Depends(get_tenant_db)):
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(visa, field, value)
    session.add(visa)
    await session.commit()
    await session.refresh(visa)
    return await _to_out(session, visa)


@router.post("/visas/{visa_id}/transition", response_model=VisaOut)
async def transition_visa_status(visa_id: UUID, body: VisaStatusTransitionIn, session: AsyncSession = Depends(get_tenant_db)):
    """
    Moves a visa application to a new status. Auto-stamps the relevant date
    field (submitted_date on -> SUBMITTED, decision_date on -> APPROVED/
    REJECTED/RECEIVED) so staff don't have to fill dates in manually on top
    of picking the status.
    """
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")

    current_order = VISA_STATUS_ORDER.get(visa.status, 0)
    new_order = VISA_STATUS_ORDER.get(body.status, 0)
    is_resubmission = visa.status == VisaStatus.REJECTED and body.status in (
        VisaStatus.DOCUMENTS_COLLECTED, VisaStatus.SUBMITTED,
    )
    if new_order < current_order and not is_resubmission and not body.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"الانتقال من '{visa.status}' إلى '{body.status}' يبدو رجوعًا للخلف. "
                "لو ده مقصود (مثلاً إعادة تقديم بعد رفض)، ابعت force=true."
            ),
        )

    visa.status = body.status
    if body.status == VisaStatus.SUBMITTED and not visa.submitted_date:
        from datetime import UTC, datetime
        visa.submitted_date = datetime.now(UTC).date()
    if body.status in (VisaStatus.APPROVED, VisaStatus.REJECTED, VisaStatus.RECEIVED) and not visa.decision_date:
        from datetime import UTC, datetime
        visa.decision_date = datetime.now(UTC).date()
    if body.status == VisaStatus.REJECTED and body.rejection_reason:
        visa.rejection_reason = body.rejection_reason

    session.add(visa)
    await session.commit()
    await session.refresh(visa)
    return await _to_out(session, visa)


@router.delete("/visas/{visa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visa(visa_id: UUID, session: AsyncSession = Depends(get_tenant_db)):
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")
    await session.delete(visa)
    await session.commit()
