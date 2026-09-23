"""
app/modules/cases/api/router.py — Generic Case Engine API Endpoints
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case, CaseContact, CaseType, Resource
from app.modules.cases.services.engine import create_case, transition_case
from app.modules.contacts.models import Contact
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/cases", tags=["Case Engine"])
resources_router = APIRouter(prefix="/resources", tags=["Case Resources"])
logger = logging.getLogger(__name__)


# ── Pydantic Schemas ───────────────────────────────────────────────────────────


class CaseContactIn(BaseModel):
    contact_id: UUID
    role: str = "primary"
    meta: dict[str, Any] = {}


class CaseCreateIn(BaseModel):
    case_type_id: UUID
    title: str | None = None
    resource_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    data: dict[str, Any] = {}
    contacts: list[CaseContactIn] = []


class TransitionIn(BaseModel):
    to_stage: str
    reason: str | None = None
    data_patch: dict[str, Any] | None = None


class ResourceCreateIn(BaseModel):
    resource_type: str
    name: str
    code: str | None = None
    attributes: dict[str, Any] = {}


# ── P1 Item 8: hospitality daily_rate=0 trap ────────────────────────────────
#
# Root cause (live-verified): CaseType.stages[...]["schema"] for hospitality
# declares "daily_rate" as a *required* field with "minimum": 0 — but that
# JSON Schema is DECORATIVE ONLY. Nothing in the backend ever actually
# validates Case.data against it (grepped the whole app/modules/cases tree —
# no jsonschema/validate call exists anywhere). So a booking can be created
# with daily_rate missing, null, or 0, which all pass the (unenforced)
# "minimum: 0" rule. At checkout, hospitality/services/folio.py silently
# does `Decimal(case_data.get("daily_rate", "0") or "0")`, producing a
# folio total of exactly 0 with no error, no warning, and no GL posting —
# a stay that generates zero revenue and looks, from the UI, identical to
# a deliberately-comped booking.
#
# Fix (agreed): at the API layer, for hospitality bookings only, if
# daily_rate is missing/<=0, auto-fill it from the selected room's
# `attributes.base_rate` (Resource.resource_type == "room"). If there is no
# room selected, or the room has no base_rate configured either, reject the
# booking with 422 rather than silently accepting a free stay. This is
# scoped to the hospitality plugin_key only — travel/rental/recruitment
# case creation is untouched.
_HOSPITALITY_PLUGIN_KEY = "hospitality"


async def _enforce_hospitality_daily_rate(
    session: AsyncSession, body: CaseCreateIn
) -> None:
    ct = await session.get(CaseType, body.case_type_id)
    if not ct or ct.plugin_key != _HOSPITALITY_PLUGIN_KEY:
        return

    raw_rate = body.data.get("daily_rate")
    try:
        rate = float(raw_rate) if raw_rate is not None else 0.0
    except (TypeError, ValueError):
        rate = 0.0

    if rate > 0:
        return

    # daily_rate is missing / null / 0 — try to auto-fill from the room.
    base_rate = None
    if body.resource_id:
        room = await session.get(Resource, body.resource_id)
        if room and room.resource_type == "room":
            attrs = room.attributes or {}
            candidate = attrs.get("base_rate")
            if candidate is not None:
                try:
                    candidate = float(candidate)
                except (TypeError, ValueError):
                    candidate = None
                if candidate and candidate > 0:
                    base_rate = candidate

    if base_rate is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "daily_rate is required and must be greater than 0 for hospitality "
                "bookings. Either send a positive daily_rate explicitly, or select "
                "a room that has a base_rate configured."
            ),
        )

    body.data = {**body.data, "daily_rate": base_rate}
    logger.info(
        "Hospitality booking: daily_rate was missing/0 — auto-filled from room "
        "%s base_rate=%s",
        body.resource_id, base_rate,
    )


# ── Follow-up P1 item: travel quick-booking $0 trap (report section 9.1) ────
#
# Root cause: the "حجز مخصص بدون باقة" (custom booking without a package) flow
# (frontend/src/app/dashboard/travel/new/page.tsx -> POST /cases) only ever
# sends {customer_name, destination, travel_date_requested,
# return_date_requested, group_size, notes, services: []} — no price field at
# all. app/plugins/travel/services/financials.py::calculate_booking_financials
# resolves price as: sum(services[].sell_price) if services is non-empty,
# else the top-level case.data["sell_price"]/["buy_price"], else 0. A case
# opened via this flow always lands on "else 0" — there is no code path that
# ever fills in a price for it. The GL posting at "confirmed"
# (app/plugins/travel/listeners.py::_post_confirmed_entries) then computes a
# real, POSTED zero-amount... no, actually skips the post outright when the
# total is <= 0 (mirroring hospitality's folio.total <= 0 guard) — so nothing
# crashes and nothing looks wrong, the booking just silently never produces
# any receivable, revenue, or commission. This is the same shape of trap as
# Item 8 (hospitality daily_rate=0), one plugin over.
#
# Design decision (mine, documented per the prompt's instruction to choose
# and justify): enforce at the CONFIRM transition, not at case-open time.
# Case-open must stay permissive — a travel case commonly starts as a bare
# inquiry ("استفسار واردة") before any price has been negotiated with the
# customer or a supplier, and forcing a price at creation would block that
# legitimate early state. "confirmed" is the stage that actually books a
# receivable against the customer (_post_confirmed_entries posts DR AR /
# CR Revenue right there), so that is the last safe point to demand a real,
# positive sell price before the case is allowed to claim it is confirmed.
_TRAVEL_PLUGIN_KEY = "travel"
_TRAVEL_CONFIRM_STAGE = "confirmed"


def _travel_total_sell_price(case_data: dict[str, Any]) -> float:
    services = case_data.get("services") or []
    if isinstance(services, list) and services:
        total = 0.0
        for svc in services:
            if not isinstance(svc, dict):
                continue
            try:
                total += float(svc.get("sell_price") or 0) * int(svc.get("quantity") or 1)
            except (TypeError, ValueError):
                continue
        return total
    try:
        return float(case_data.get("sell_price") or 0)
    except (TypeError, ValueError):
        return 0.0


async def _enforce_travel_confirmed_pricing(
    session: AsyncSession, case: Case, ct: CaseType, body: TransitionIn
) -> None:
    if ct.plugin_key != _TRAVEL_PLUGIN_KEY or body.to_stage != _TRAVEL_CONFIRM_STAGE:
        return

    effective_data = {**case.data, **(body.data_patch or {})}
    if _travel_total_sell_price(effective_data) > 0:
        return

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "Cannot confirm a travel booking with no priced services and no "
            "sell_price set. Add at least one service with a positive "
            "sell_price (or a top-level sell_price) via data_patch before "
            "confirming — otherwise the booking can never post a receivable "
            "or revenue entry."
        ),
    )


# ── Case CRUD ─────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_case(
    body: CaseCreateIn,
    request: Request,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Opens a new Case in the configured initial stage."""
    tenant_id: str = request.state.tenant_id
    user_id: str | None = request.state.current_user_id

    await _enforce_hospitality_daily_rate(session, body)

    case = await create_case(
        session,
        tenant_id=tenant_id,
        case_type_id=body.case_type_id,
        title=body.title,
        resource_id=body.resource_id,
        start_date=body.start_date,
        end_date=body.end_date,
        data=body.data,
        contacts=[c.model_dump() for c in body.contacts],
        created_by=UUID(user_id) if user_id else None,
    )
    await session.commit()
    await session.refresh(case)
    return case


@router.get("")
async def list_cases(
    current_user: CurrentUser,
    case_type_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(default=100, le=500, description="Maximum records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    session: AsyncSession = Depends(get_tenant_db),
):
    """Lists Cases, optionally filtered by type and status. Supports limit/offset pagination."""
    q = select(Case)
    if case_type_id:
        q = q.where(Case.case_type_id == case_type_id)
    if status:
        q = q.where(Case.status == status.upper())
    q = q.order_by(Case.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/{id}")
async def get_case(id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_tenant_db)):
    """Fetches a single Case with full stage history and contacts."""
    case = await session.get(Case, id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


@router.post("/{id}/transition")
async def transition(
    id: UUID,
    body: TransitionIn,
    request: Request,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    The critical transition endpoint. Moves the Case to the next stage,
    validates the move against the CaseType state machine, prevents double-booking,
    and publishes a CaseStageTransitionedEvent to the EventBus.
    """
    tenant_id: str = request.state.tenant_id
    user_id: str | None = request.state.current_user_id

    existing_case = await session.get(Case, id)
    if not existing_case:
        raise HTTPException(status_code=404, detail=f"Case {id} not found.")
    ct = await session.get(CaseType, existing_case.case_type_id)
    if ct:
        await _enforce_travel_confirmed_pricing(session, existing_case, ct, body)

    case = await transition_case(
        session,
        tenant_id=tenant_id,
        case_id=id,
        to_stage=body.to_stage,
        reason=body.reason,
        data_patch=body.data_patch,
        changed_by=UUID(user_id) if user_id else None,
    )
    await session.commit()
    return {
        "case_id": str(case.id),
        "current_stage": case.current_stage,
        "status": case.status,
    }


@router.post("/{id}/contacts", status_code=status.HTTP_201_CREATED)
async def add_contact(
    id: UUID,
    body: CaseContactIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Associates a Contact with a role to an existing Case."""
    case = await session.get(Case, id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    # Verify the contact actually belongs to this tenant's schema before
    # linking — previously any UUID was accepted unchecked, which could
    # silently create a CaseContact row pointing at nothing (or, if IDs
    # were ever guessable across environments, at least a needless
    # dangling reference).
    contact = await session.get(Contact, body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")

    link = CaseContact(
        case_id=id,
        contact_id=body.contact_id,
        role=body.role,
        meta=body.meta,
    )
    session.add(link)
    await session.commit()
    return {"message": "Contact added."}


# ── Resource CRUD ─────────────────────────────────────────────────────────────


@resources_router.post("", status_code=status.HTTP_201_CREATED)
async def create_resource(
    body: ResourceCreateIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Creates a new bookable Resource (room, vehicle, etc.)."""
    resource = Resource(
        resource_type=body.resource_type,
        name=body.name,
        code=body.code,
        attributes=body.attributes,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return resource


@resources_router.get("")
async def list_resources(
    current_user: CurrentUser,
    resource_type: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Lists all Resources, optionally filtered by type and availability."""
    q = select(Resource)
    if resource_type:
        q = q.where(Resource.resource_type == resource_type)
    if status:
        q = q.where(Resource.status == status.upper())
    result = await session.execute(q)
    return result.scalars().all()


@resources_router.get("/{id}")
async def get_resource(id: UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_tenant_db)):
    resource = await session.get(Resource, id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found.")
    return resource
