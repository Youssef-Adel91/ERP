"""
app/plugins/travel/api_passengers.py — Structured Passenger Manifest API

Provides full CRUD for TravelPassenger records attached to a booking Case.
Works alongside the existing JSONB passenger_manifest in Case.data — does
NOT replace it.

Why:
  The JSONB manifest in Case.data is a flat, hard-to-edit blob. Staff need
  to add a passenger, fix a passport number, or link an existing passenger
  to their visa record — all of which require per-record endpoints, not
  a full manifest overwrite.

DECOUPLING CONTRACT:
  ✅ FK to Case (booking) and optionally VisaApplication
  ✅ Soft delete for passengers linked to a visa (is_active=False)
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case
from app.modules.system.dependencies import CurrentUser
from app.plugins.travel.models.passenger import TravelPassenger

router = APIRouter(prefix="/travel", tags=["Travel Plugin — Passengers"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class PassengerIn(BaseModel):
    full_name: str
    full_name_ar: str | None = None
    passport_number: str | None = None
    passport_expiry: date | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    gender: str | None = None          # male / female
    passenger_type: str = "adult"      # adult / child / infant
    visa_application_id: UUID | None = None


class PassengerPatchIn(BaseModel):
    full_name: str | None = None
    full_name_ar: str | None = None
    passport_number: str | None = None
    passport_expiry: date | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    gender: str | None = None
    passenger_type: str | None = None
    visa_application_id: UUID | None = None


class PassengerOut(BaseModel):
    id: UUID
    case_id: UUID
    full_name: str
    full_name_ar: str | None
    passport_number: str | None
    passport_expiry: date | None
    date_of_birth: date | None
    nationality: str | None
    gender: str | None
    passenger_type: str
    visa_application_id: UUID | None
    is_active: bool

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_case_or_404(session: AsyncSession, case_id: UUID) -> Case:
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="الحجز غير موجود.")
    return case


async def _get_passenger_or_404(
    session: AsyncSession, passenger_id: UUID, case_id: UUID
) -> TravelPassenger:
    passenger = await session.get(TravelPassenger, passenger_id)
    if not passenger or passenger.case_id != case_id:
        raise HTTPException(status_code=404, detail="الراكب غير موجود في هذا الحجز.")
    if not passenger.is_active:
        raise HTTPException(status_code=410, detail="الراكب محذوف.")
    return passenger


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/cases/{case_id}/passengers", response_model=list[PassengerOut])
async def list_passengers(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> list[PassengerOut]:
    """Lists all active passengers for a booking."""
    await _get_case_or_404(session, case_id)
    result = await session.execute(
        select(TravelPassenger)
        .where(TravelPassenger.case_id == case_id)
        .where(TravelPassenger.is_active == True)  # noqa: E712
        .order_by(TravelPassenger.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/cases/{case_id}/passengers",
    response_model=PassengerOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_passenger(
    case_id: UUID,
    body: PassengerIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> PassengerOut:
    """Adds a new passenger to a booking."""
    await _get_case_or_404(session, case_id)
    passenger = TravelPassenger(case_id=case_id, **body.model_dump())
    session.add(passenger)
    await session.commit()
    await session.refresh(passenger)
    return passenger


@router.get("/cases/{case_id}/passengers/{passenger_id}", response_model=PassengerOut)
async def get_passenger(
    case_id: UUID,
    passenger_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> PassengerOut:
    """Gets a single passenger record."""
    return await _get_passenger_or_404(session, passenger_id, case_id)


@router.patch("/cases/{case_id}/passengers/{passenger_id}", response_model=PassengerOut)
async def update_passenger(
    case_id: UUID,
    passenger_id: UUID,
    body: PassengerPatchIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> PassengerOut:
    """Updates passenger details (partial update)."""
    passenger = await _get_passenger_or_404(session, passenger_id, case_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(passenger, field, value)
    session.add(passenger)
    await session.commit()
    await session.refresh(passenger)
    return passenger


@router.delete(
    "/cases/{case_id}/passengers/{passenger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_passenger(
    case_id: UUID,
    passenger_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Deletes a passenger from a booking.

    Soft delete (is_active=False) if the passenger is linked to a
    VisaApplication — the visa record needs the passenger reference intact.
    Hard delete otherwise (e.g. passenger added by mistake with no visa).
    """
    passenger = await _get_passenger_or_404(session, passenger_id, case_id)

    if passenger.visa_application_id is not None:
        # Soft delete — preserve linkage to the visa record
        passenger.is_active = False
        session.add(passenger)
        await session.commit()
    else:
        await session.delete(passenger)
        await session.commit()
