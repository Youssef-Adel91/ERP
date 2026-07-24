"""
app/modules/contacts/router.py — Contacts CRM API Routes

All routes require a valid Bearer token (TenantMiddleware resolves tenant_id).
The `get_tenant_db` dependency automatically executes:
    SET search_path TO tenant_{id}, public
before yielding the session, so all ORM queries hit the correct schema.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.modules.contacts.models import Contact, ContactStatus, ContactType
from app.modules.contacts.schemas import (
    ContactCreateRequest,
    ContactListResponse,
    ContactResponse,
    ContactUpdateRequest,
)
from app.modules.system.dependencies import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter()


# ── POST / — Create Contact ───────────────────────────────────────────────────


@router.post(
    "/",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contact (customer or supplier)",
    description=(
        "Inserts a new Contact into the **tenant's schema**.\n\n"
        "The `get_tenant_db` dependency ensures the session targets "
        "`tenant_{id}.contacts`, not `public.contacts`.\n\n"
        "On creation, a `contact.created` event is published for "
        "future Trust Network processing."
    ),
)
async def create_contact(
    data: ContactCreateRequest,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ContactResponse:
    """Insert a Contact row in the tenant schema and return it."""
    contact = Contact(
        contact_type=data.contact_type,
        name=data.name,
        name_ar=data.name_ar,
        phone=data.phone,
        phone_alt=data.phone_alt,
        email=data.email,
        national_id=data.national_id,
        created_by=current_user.id,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    logger.info(
        "Created contact '%s' (type=%s, id=%s) in schema for tenant=%s",
        contact.name,
        contact.contact_type,
        contact.id,
        request.state.tenant_id,
    )

    return ContactResponse.model_validate(contact)


# ── GET / — List Contacts ─────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=ContactListResponse,
    summary="List contacts with filtering and pagination",
)
async def list_contacts(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    contact_type: ContactType | None = Query(default=None),
    status: ContactStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, description="Search by name or phone"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ContactListResponse:
    """
    List all contacts in the tenant's schema.

    Supports:
      - Filter by `contact_type` (customer / supplier)
      - Filter by `status` (active / blocked / archived)
      - Full-text search on `name` (case-insensitive ILIKE)
      - Pagination via `limit` + `offset`
    """
    # ── Build WHERE clause ────────────────────────────────────────────────────
    filters = []
    if contact_type:
        filters.append(Contact.contact_type == contact_type)
    if status:
        filters.append(Contact.status == status)
    if search:
        filters.append(Contact.name.ilike(f"%{search}%"))

    # ── Count query ───────────────────────────────────────────────────────────
    count_result = await db.execute(
        select(func.count()).select_from(Contact).where(*filters)
    )
    total = count_result.scalar_one()

    # ── Data query ────────────────────────────────────────────────────────────
    result = await db.execute(
        select(Contact)
        .where(*filters)
        .order_by(Contact.name)
        .limit(limit)
        .offset(offset)
    )
    contacts = result.scalars().all()

    return ContactListResponse(
        total=total,
        items=[ContactResponse.model_validate(c) for c in contacts],
    )


# ── GET /{id} — Get Contact by ID ────────────────────────────────────────────


@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Get a single contact by ID",
)
async def get_contact(
    contact_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ContactResponse:
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact '{contact_id}' not found.",
        )

    return ContactResponse.model_validate(contact)


# ── PATCH /{id} — Update Contact ──────────────────────────────────────────────


@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Partially update a contact",
)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ContactResponse:
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact '{contact_id}' not found.",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return ContactResponse.model_validate(contact)
