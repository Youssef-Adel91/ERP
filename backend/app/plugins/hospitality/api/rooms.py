"""
app/plugins/hospitality/api/rooms.py — Room Management API

Maps hotel rooms to the Core Resource table (resource_type = "room").
The JSONB `attributes` field stores vertical-specific room metadata:
  capacity, floor, room_type, amenities, smoking, etc.

This is the ONLY place the hospitality plugin creates/reads resources.
The core engine's double-booking prevention operates on the Resource rows.

DECOUPLING CONTRACT:
  ✅ Reads/writes only app.modules.cases.models.core.Resource
  ✅ Filters strictly by resource_type="room" and tenant's schema
  ❌ Never bypasses the core engine's overlap lock
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.core.security.security import require_role
from app.modules.cases.models.core import Case, Resource
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import UserRole

router = APIRouter(prefix="/hospitality", tags=["Hospitality – Rooms"])

# ── Room type & floor enums (stored in JSONB — not SAEnum to avoid migrations) ─

ROOM_TYPES = {"single", "double", "twin", "suite", "deluxe", "family", "studio", "penthouse"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class RoomAttributes(BaseModel):
    """Stored in Resource.attributes (JSONB). All fields are optional extras."""
    capacity: int = Field(default=1, ge=1, le=20, description="Maximum guest count")
    floor: int = Field(default=1, ge=0)
    room_type: str = Field(default="double")
    view: str | None = None          # sea_view, pool_view, garden_view, city_view
    bed_type: str | None = None      # king, queen, twin, single
    has_balcony: bool = False
    is_smoking: bool = False
    amenities: list[str] = Field(default_factory=list)  # wifi, ac, minibar, jacuzzi …
    base_rate: float | None = None   # Default daily rate suggestion


class RoomCreate(BaseModel):
    code: str = Field(max_length=20, description="Room number / identifier, e.g. '101', 'Suite-A'")
    name: str = Field(max_length=255)
    name_ar: str | None = None
    attributes: RoomAttributes = Field(default_factory=RoomAttributes)


class RoomUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    is_active: bool | None = None
    attributes: RoomAttributes | None = None


class RoomOut(BaseModel):
    id: str
    code: str
    name: str
    name_ar: str | None
    is_active: bool
    attributes: dict[str, Any]

    model_config = {"from_attributes": True}


class RoomAvailabilityOut(RoomOut):
    is_available: bool
    conflicting_case_id: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resource_to_out(r: Resource) -> dict:
    attrs = dict(r.attributes or {})
    # Resource has neither a boolean is_active column nor a name_ar column —
    # only id/resource_type/name/code/status/attributes exist on the real
    # table. Both are stored inside the JSONB `attributes` dict under a
    # reserved "_name_ar" key (status handles is_active, see below) so no
    # schema migration is needed. Excluded from the public `attributes` echo.
    name_ar = attrs.pop("_name_ar", None)
    return {
        "id": str(r.id),
        "code": r.code,
        "name": r.name,
        "name_ar": name_ar,
        # ResourceStatus: AVAILABLE/OCCUPIED/MAINTENANCE — this module treats
        # a "INACTIVE" status string as the soft-delete marker, the closest
        # equivalent that doesn't require a schema migration.
        "is_active": r.status != "INACTIVE",
        "attributes": attrs,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/rooms", response_model=list[RoomOut])
async def list_rooms(
    current_user: CurrentUser,
    room_type: str | None = Query(None),
    floor: int | None = Query(None),
    min_capacity: int | None = Query(None),
    is_active: bool = Query(True),
    session: AsyncSession = Depends(get_tenant_db),
):
    """List hotel rooms with optional filtering by type, floor, and capacity."""
    stmt = select(Resource).where(Resource.resource_type == "room")
    stmt = stmt.where(Resource.status != "INACTIVE") if is_active else stmt.where(Resource.status == "INACTIVE")
    rooms = (await session.scalars(stmt)).all()

    # Apply JSONB attribute filters in Python (avoids vendor-specific JSON SQL)
    results = []
    for r in rooms:
        attrs = r.attributes or {}
        if room_type and attrs.get("room_type") != room_type:
            continue
        if floor is not None and attrs.get("floor") != floor:
            continue
        if min_capacity is not None and (attrs.get("capacity") or 1) < min_capacity:
            continue
        results.append(_resource_to_out(r))

    return results


@router.get("/rooms/availability", response_model=list[RoomAvailabilityOut])
async def check_room_availability(
    current_user: CurrentUser,
    check_in: str = Query(..., description="ISO date, e.g. 2024-12-25"),
    check_out: str = Query(..., description="ISO date, e.g. 2024-12-28"),
    min_capacity: int = Query(1),
    room_type: str | None = Query(None),
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Returns all rooms with an `is_available` flag for the requested date range.

    Availability logic mirrors the core engine's _check_resource_availability():
      overlap condition: existing.start < requested_out AND existing.end > requested_in
    """
    from datetime import date
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use ISO dates (YYYY-MM-DD).")

    if co <= ci:
        raise HTTPException(status_code=422, detail="check_out must be after check_in.")

    # Fetch all active rooms
    stmt = select(Resource).where(
        Resource.resource_type == "room",
        Resource.status != "INACTIVE",
    )
    rooms = (await session.scalars(stmt)).all()

    # Fetch all non-cancelled/non-closed reservations that overlap the window
    # A reservation overlaps if: case.start_date < co AND case.end_date > ci
    from sqlalchemy import cast, Date
    conflict_stmt = (
        select(Case.resource_id, Case.id)
        .where(
            Case.resource_id.isnot(None),
            Case.status.notin_(["CANCELLED", "CLOSED"]),
            cast(Case.start_date, Date) < co,
            cast(Case.end_date, Date) > ci,
        )
    )
    conflict_rows = (await session.execute(conflict_stmt)).all()
    # resource_id → first conflicting case_id
    conflicts: dict[uuid.UUID, uuid.UUID] = {r.resource_id: r.id for r in conflict_rows}

    results = []
    for r in rooms:
        attrs = r.attributes or {}
        if room_type and attrs.get("room_type") != room_type:
            continue
        if (attrs.get("capacity") or 1) < min_capacity:
            continue
        conflict_id = conflicts.get(r.id)
        results.append({
            **_resource_to_out(r),
            "is_available": conflict_id is None,
            "conflicting_case_id": str(conflict_id) if conflict_id else None,
        })

    return results


@router.get("/rooms/{room_id}", response_model=RoomOut)
async def get_room(room_id: uuid.UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_tenant_db)):
    room = await session.get(Resource, room_id)
    if not room or room.resource_type != "room":
        raise HTTPException(status_code=404, detail="Room not found.")
    return _resource_to_out(room)


@router.post(
    "/rooms",
    response_model=RoomOut,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def create_room(body: RoomCreate, current_user: CurrentUser, session: AsyncSession = Depends(get_tenant_db)):
    """Create a new hotel room. The room code must be unique within the tenant."""
    existing = await session.execute(
        select(Resource).where(
            Resource.resource_type == "room",
            Resource.code == body.code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Room '{body.code}' already exists.")

    room_attrs = body.attributes.model_dump()
    if body.name_ar:
        room_attrs["_name_ar"] = body.name_ar
    room = Resource(
        resource_type="room",
        code=body.code,
        name=body.name,
        status="AVAILABLE",
        attributes=room_attrs,
    )
    session.add(room)
    await session.flush()
    await session.commit()
    return _resource_to_out(room)


@router.patch(
    "/rooms/{room_id}",
    response_model=RoomOut,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def update_room(
    room_id: uuid.UUID,
    body: RoomUpdate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    room = await session.get(Resource, room_id)
    if not room or room.resource_type != "room":
        raise HTTPException(status_code=404, detail="Room not found.")

    if body.name is not None:
        room.name = body.name
    if body.is_active is not None:
        room.status = "INACTIVE" if not body.is_active else "AVAILABLE"
    if body.attributes is not None:
        room.attributes = {**(room.attributes or {}), **body.attributes.model_dump(exclude_none=True)}
    if body.name_ar is not None:
        room.attributes = {**(room.attributes or {}), "_name_ar": body.name_ar}

    await session.commit()
    return _resource_to_out(room)


@router.delete(
    "/rooms/{room_id}",
    status_code=204,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def deactivate_room(room_id: uuid.UUID, current_user: CurrentUser, session: AsyncSession = Depends(get_tenant_db)):
    """Soft-delete: sets is_active=False. Active reservations are NOT cancelled."""
    room = await session.get(Resource, room_id)
    if not room or room.resource_type != "room":
        raise HTTPException(status_code=404, detail="Room not found.")
    room.status = "INACTIVE"
    await session.commit()
