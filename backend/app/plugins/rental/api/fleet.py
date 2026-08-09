"""
app/plugins/rental/api/fleet.py — Fleet Management API

Maps rental vehicles to the Core Resource table (resource_type = "vehicle").
The JSONB `attributes` field stores vertical-specific data:
  plate_number, make, model, year, color, vin, current_mileage, status.

DECOUPLING CONTRACT:
  ✅ Reads/writes only app.modules.cases.models.core.Resource
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case, Resource

router = APIRouter(prefix="/rental", tags=["Rental – Fleet"])


class VehicleAttributes(BaseModel):
    plate_number: str = Field(..., description="License plate")
    make: str = Field(..., description="e.g. Toyota")
    model: str = Field(..., description="e.g. Corolla")
    year: int = Field(..., ge=1990)
    color: str | None = None
    vin: str | None = None
    current_mileage: int = Field(default=0, ge=0)
    transmission: str = Field(default="automatic")
    fuel_type: str = Field(default="petrol")
    daily_rate_suggested: float | None = None


class VehicleCreate(BaseModel):
    code: str = Field(max_length=50, description="Internal Fleet ID (e.g., V-001)")
    name: str = Field(max_length=255, description="Display Name (e.g., Toyota Corolla 2023)")
    name_ar: str | None = None
    attributes: VehicleAttributes


class VehicleUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    is_active: bool | None = None
    attributes: VehicleAttributes | None = None


class VehicleOut(BaseModel):
    id: str
    code: str
    name: str
    name_ar: str | None
    is_active: bool
    attributes: dict[str, Any]

    model_config = {"from_attributes": True}


class VehicleAvailabilityOut(VehicleOut):
    is_available: bool
    conflicting_case_id: str | None = None


def _resource_to_out(r: Resource) -> dict:
    return {
        "id": str(r.id),
        "code": r.code,
        "name": r.name,
        "name_ar": r.name_ar,
        "is_active": r.is_active,
        "attributes": r.attributes or {},
    }


@router.get("/fleet", response_model=list[VehicleOut])
async def list_fleet(
    make: str | None = Query(None),
    is_active: bool = Query(True),
    session: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(Resource).where(
        Resource.resource_type == "vehicle",
        Resource.is_active == is_active,
    )
    vehicles = (await session.scalars(stmt)).all()

    results = []
    for v in vehicles:
        attrs = v.attributes or {}
        if make and attrs.get("make") != make:
            continue
        results.append(_resource_to_out(v))
    return results


@router.get("/fleet/availability", response_model=list[VehicleAvailabilityOut])
async def check_vehicle_availability(
    pickup_date: str = Query(..., description="ISO date, e.g. 2024-12-25"),
    return_date: str = Query(..., description="ISO date, e.g. 2024-12-28"),
    session: AsyncSession = Depends(get_tenant_db),
):
    from datetime import date
    try:
        ci = date.fromisoformat(pickup_date)
        co = date.fromisoformat(return_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format.")

    if co <= ci:
        raise HTTPException(status_code=422, detail="return_date must be after pickup_date.")

    stmt = select(Resource).where(
        Resource.resource_type == "vehicle",
        Resource.is_active == True,
    )
    vehicles = (await session.scalars(stmt)).all()

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
    conflicts: dict[uuid.UUID, uuid.UUID] = {r.resource_id: r.id for r in conflict_rows}

    results = []
    for v in vehicles:
        conflict_id = conflicts.get(v.id)
        results.append({
            **_resource_to_out(v),
            "is_available": conflict_id is None,
            "conflicting_case_id": str(conflict_id) if conflict_id else None,
        })
    return results


@router.post("/fleet", response_model=VehicleOut, status_code=201)
async def add_vehicle(body: VehicleCreate, session: AsyncSession = Depends(get_tenant_db)):
    existing = await session.execute(
        select(Resource).where(
            Resource.resource_type == "vehicle",
            Resource.code == body.code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Vehicle '{body.code}' already exists.")

    vehicle = Resource(
        resource_type="vehicle",
        code=body.code,
        name=body.name,
        name_ar=body.name_ar,
        is_active=True,
        attributes=body.attributes.model_dump(),
    )
    session.add(vehicle)
    await session.commit()
    return _resource_to_out(vehicle)


@router.patch("/fleet/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    body: VehicleUpdate,
    session: AsyncSession = Depends(get_tenant_db),
):
    vehicle = await session.get(Resource, vehicle_id)
    if not vehicle or vehicle.resource_type != "vehicle":
        raise HTTPException(status_code=404, detail="Vehicle not found.")

    if body.name is not None:
        vehicle.name = body.name
    if body.name_ar is not None:
        vehicle.name_ar = body.name_ar
    if body.is_active is not None:
        vehicle.is_active = body.is_active
    if body.attributes is not None:
        vehicle.attributes = {**(vehicle.attributes or {}), **body.attributes.model_dump(exclude_none=True)}

    await session.commit()
    return _resource_to_out(vehicle)


@router.delete("/fleet/{vehicle_id}", status_code=204)
async def deactivate_vehicle(vehicle_id: uuid.UUID, session: AsyncSession = Depends(get_tenant_db)):
    """Soft-delete: sets is_active=False. Active rental cases are NOT cancelled —
    this only removes the vehicle from future availability/booking searches
    (mirrors hospitality's deactivate_room)."""
    vehicle = await session.get(Resource, vehicle_id)
    if not vehicle or vehicle.resource_type != "vehicle":
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    vehicle.is_active = False
    await session.commit()
