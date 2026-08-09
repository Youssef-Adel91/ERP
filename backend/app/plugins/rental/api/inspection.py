"""
app/plugins/rental/api/inspection.py — Handover Inspection API

Submit pickup and return inspections.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case
from app.plugins.rental.models.inspection import FuelLevel, InspectionType, VehicleInspection
from app.plugins.rental.services.inspection import diff_inspections, InspectionDiff

router = APIRouter(prefix="/rental", tags=["Rental – Inspection"])


class DamageNote(BaseModel):
    location: str
    type: str
    severity: str | None = None
    photo_url: str | None = None


class InspectionCreate(BaseModel):
    inspection_type: InspectionType
    mileage: int = Field(..., ge=0)
    fuel_level: FuelLevel
    damage_notes: list[DamageNote] = Field(default_factory=list)
    inspected_by: str | None = None
    notes: str | None = None


class InspectionOut(BaseModel):
    id: str
    case_id: str
    inspection_type: str
    mileage: int
    fuel_level: str
    damage_notes: list[dict[str, Any]] | None
    inspected_by: str | None
    inspected_at: str
    notes: str | None

    model_config = {"from_attributes": True}


@router.post("/cases/{case_id}/inspections", response_model=InspectionOut)
async def create_inspection(
    case_id: uuid.UUID,
    body: InspectionCreate,
    session: AsyncSession = Depends(get_tenant_db),
):
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Rental case not found.")

    # Check for existing inspection of the same type
    existing = await session.execute(
        select(VehicleInspection).where(
            VehicleInspection.case_id == case_id,
            VehicleInspection.inspection_type == body.inspection_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"A {body.inspection_type.value} inspection already exists.")

    inspection = VehicleInspection(
        case_id=case_id,
        inspection_type=body.inspection_type,
        mileage=body.mileage,
        fuel_level=body.fuel_level,
        damage_notes=[d.model_dump() for d in body.damage_notes],
        inspected_by=body.inspected_by,
        notes=body.notes,
    )
    session.add(inspection)
    
    # Mark inspection completed in case data
    if body.inspection_type == InspectionType.PICKUP:
        case.data = {**case.data, "pickup_inspection_completed": True}
    else:
        case.data = {**case.data, "return_inspection_completed": True}
    session.add(case)
    
    await session.commit()
    
    return {
        "id": str(inspection.id),
        "case_id": str(inspection.case_id),
        "inspection_type": inspection.inspection_type.value,
        "mileage": int(inspection.mileage),
        "fuel_level": inspection.fuel_level.value,
        "damage_notes": inspection.damage_notes,
        "inspected_by": inspection.inspected_by,
        "inspected_at": inspection.inspected_at.isoformat(),
        "notes": inspection.notes,
    }


@router.get("/cases/{case_id}/inspections", response_model=list[InspectionOut])
async def list_inspections(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(VehicleInspection).where(VehicleInspection.case_id == case_id)
    inspections = (await session.scalars(stmt)).all()
    
    return [
        {
            "id": str(ins.id),
            "case_id": str(ins.case_id),
            "inspection_type": ins.inspection_type.value,
            "mileage": int(ins.mileage),
            "fuel_level": ins.fuel_level.value,
            "damage_notes": ins.damage_notes,
            "inspected_by": ins.inspected_by,
            "inspected_at": ins.inspected_at.isoformat(),
            "notes": ins.notes,
        }
        for ins in inspections
    ]


@router.get("/cases/{case_id}/inspections/diff", response_model=InspectionDiff)
async def get_inspection_diff(
    case_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_db),
):
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Rental case not found.")

    from app.modules.cases.models.core import CaseType
    ct = await session.get(CaseType, case.case_type_id)
    
    diff = await diff_inspections(session, case_id, case.data, ct.meta if ct else {})
    if not diff:
        raise HTTPException(400, "Both pickup and return inspections are required to calculate diff.")
    
    return diff
