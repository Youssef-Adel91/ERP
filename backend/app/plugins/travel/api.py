"""
app/plugins/travel/api.py — Travel Plugin REST API
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.plugins.travel.bootstrap import bootstrap_travel_case_type
from app.plugins.travel.services.financials import calculate_booking_financials
from app.modules.cases.models.core import Case

router = APIRouter(prefix="/travel", tags=["Travel Plugin"])


@router.post("/bootstrap")
async def activate_plugin(session: AsyncSession = Depends(get_tenant_db)):
    """Idempotent: injects the 'travel_booking' CaseType into the core engine."""
    ct = await bootstrap_travel_case_type(session)
    await session.commit()
    return {"message": "Travel plugin activated.", "case_type_id": str(ct.id)}


@router.get("/bookings/{case_id}/financials")
async def get_booking_financials(
    case_id: UUID,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Returns a typed financial summary for a travel booking Case:
    buy price, sell price, margin, commission, and per-service breakdown.
    """
    from fastapi import HTTPException
    from app.modules.cases.models.core import CaseType

    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Booking not found.")

    ct = await session.get(CaseType, case.case_type_id)
    meta = ct.meta if ct else {}

    financials = calculate_booking_financials(
        case_id=str(case_id),
        case_data=case.data,
        meta=meta,
    )
    return financials
