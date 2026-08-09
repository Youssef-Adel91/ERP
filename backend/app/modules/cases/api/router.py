"""
app/modules/cases/api/router.py — Generic Case Engine API Endpoints
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
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


# ── Case CRUD ─────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_case(
    body: CaseCreateIn,
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Opens a new Case in the configured initial stage."""
    tenant_id: str = request.state.tenant_id
    user_id: str | None = request.state.current_user_id

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
    session: AsyncSession = Depends(get_tenant_db),
):
    """Lists all Cases, optionally filtered by type and status."""
    q = select(Case)
    if case_type_id:
        q = q.where(Case.case_type_id == case_type_id)
    if status:
        q = q.where(Case.status == status.upper())
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
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    The critical transition endpoint. Moves the Case to the next stage,
    validates the move against the CaseType state machine, prevents double-booking,
    and publishes a CaseStageTransitionedEvent to the EventBus.
    """
    tenant_id: str = request.state.tenant_id
    user_id: str | None = request.state.current_user_id

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
