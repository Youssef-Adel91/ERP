"""
app/plugins/travel/api.py — Travel Plugin REST API

Changes in this revision (Travel Readiness Wave):
  - All endpoints now require authentication (CurrentUser).
  - New GET /travel/bookings/{case_id}/pdf endpoint — returns a printable
    A4 booking confirmation as application/pdf.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case
from app.modules.system.dependencies import CurrentUser
from app.plugins.travel.bootstrap import bootstrap_travel_case_type
from app.plugins.travel.services.financials import calculate_booking_financials
from app.plugins.travel.services.pdf_builder import build_booking_confirmation_pdf

router = APIRouter(prefix="/travel", tags=["Travel Plugin"])


@router.post("/bootstrap")
async def activate_plugin(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Idempotent: injects the 'travel_booking' CaseType into the core engine."""
    ct = await bootstrap_travel_case_type(session)
    await session.commit()
    return {"message": "Travel plugin activated.", "case_type_id": str(ct.id)}


@router.get("/bookings/{case_id}/financials")
async def get_booking_financials(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Returns a typed financial summary for a travel booking Case:
    buy price, sell price, margin, commission, and per-service breakdown.
    """
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Booking not found.")

    from app.modules.cases.models.core import CaseType
    ct = await session.get(CaseType, case.case_type_id)
    meta = ct.meta if ct else {}

    financials = calculate_booking_financials(
        case_id=str(case_id),
        case_data=case.data,
        meta=meta,
    )
    # The internal CaseFinancials model (financials.py) uses
    # total_buy_price/total_sell_price/total_margin/commission_amount —
    # those exact names are relied on by the GL posting listener
    # (listeners.py). Previously this endpoint remapped them down to
    # shorter buy_price/sell_price/margin/commission keys, but the
    # dashboard/travel/page.tsx TravelFinancials interface (and the
    # margin/profit KPI it feeds) expects the full total_*/margin_pct/
    # commission_amount names, so those fields always came back
    # `undefined` there. We now pass the CaseFinancials field names
    # straight through unchanged, matching every frontend consumer.
    return {
        "case_id": financials.case_id,
        "total_buy_price": financials.total_buy_price,
        "total_sell_price": financials.total_sell_price,
        "total_margin": financials.total_margin,
        "margin_pct": financials.margin_pct,
        "commission_amount": financials.commission_amount,
        "currency": financials.currency,
        "service_lines": financials.service_lines,
        "passenger_count": financials.passenger_count,
        "passenger_manifest": financials.passenger_manifest,
    }


@router.get("/bookings/{case_id}/pdf")
async def get_booking_confirmation_pdf(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Generates and returns a printable A4 PDF booking confirmation for a
    travel booking Case.

    The PDF includes: booking reference, customer name, destination, travel
    dates, services breakdown, financial summary, and passenger list.
    """
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="الحجز غير موجود.")

    from app.modules.cases.models.core import CaseType
    ct = await session.get(CaseType, case.case_type_id)
    meta = ct.meta if ct else {}

    financials = calculate_booking_financials(
        case_id=str(case_id),
        case_data=case.data,
        meta=meta,
    )

    # Build services list for the PDF from the financial service_lines
    services = [
        {
            "service_type": sl.service_type,
            "supplier_name": sl.supplier_name,
            "description": sl.description,
            "sell_price": float(sl.sell_price),
            "currency": sl.currency,
            "quantity": sl.quantity,
        }
        for sl in financials.service_lines
    ]

    # Build passengers list
    passengers = [
        {
            "full_name": p.full_name,
            "passport_number": p.passport_number,
            "nationality": p.nationality,
            "passenger_type": p.passenger_type,
        }
        for p in financials.passenger_manifest
    ]

    case_data = case.data or {}
    pdf_bytes = build_booking_confirmation_pdf(
        booking_ref=str(case_id)[:8].upper(),
        customer_name=case_data.get("customer_name") or case.title or "—",
        destination=case_data.get("destination") or "—",
        origin=case_data.get("origin"),
        travel_date=case_data.get("travel_date_requested"),
        return_date=case_data.get("return_date_requested"),
        current_stage=case.current_stage or "—",
        currency=financials.currency,
        services=services,
        total_sell_price=financials.total_sell_price,
        total_buy_price=financials.total_buy_price,
        passengers=passengers or None,
    )

    filename = f"booking_{str(case_id)[:8]}_confirmation.pdf"
    import io
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
