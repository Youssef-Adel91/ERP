"""
app/plugins/hospitality/api/__init__.py
app/plugins/hospitality/api/folio.py — Folio Management API
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.plugins.hospitality.models.folio import FolioItem, FolioItemCategory
from app.plugins.hospitality.services.folio import calculate_folio_total, post_extra_charge
from app.modules.cases.models.core import Case, CaseType
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/hospitality", tags=["Hospitality – Folio"])


class FolioItemCreate(BaseModel):
    category: FolioItemCategory
    description: str
    amount: Decimal
    currency: str = "EGP"
    quantity: Decimal = Decimal("1")
    posted_by: str | None = None
    notes: str | None = None


@router.get("/reservations/{case_id}/folio")
async def get_folio(case_id: uuid.UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_tenant_db)):
    """Returns a full computed folio for a room reservation."""
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    ct = await session.get(CaseType, case.case_type_id)
    meta = ct.meta if ct else {}
    folio = await calculate_folio_total(
        session=session,
        case_id=case_id,
        case_data=case.data,
        case_start=case.start_date,
        case_end=case.end_date,
        meta=meta,
    )
    return folio


@router.post("/reservations/{case_id}/folio/items", status_code=201)
async def add_folio_item(
    case_id: uuid.UUID,
    body: FolioItemCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Posts a single extra charge (restaurant, laundry, minibar, etc.) to the folio."""
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    if case.current_stage not in ("checked_in", "confirmed", "booked"):
        raise HTTPException(
            status_code=409,
            detail="Cannot post charges to a reservation that is checked out, closed, or cancelled.",
        )
    item = await post_extra_charge(
        session=session,
        case_id=case_id,
        category=body.category,
        description=body.description,
        amount=body.amount,
        currency=body.currency,
        quantity=body.quantity,
        posted_by=body.posted_by,
        notes=body.notes,
    )
    await session.commit()
    return {"id": str(item.id), "amount": float(item.amount), "category": item.category.value}
