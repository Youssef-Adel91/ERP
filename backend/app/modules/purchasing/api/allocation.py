"""
app/modules/purchasing/api/allocation.py — Landed Cost Allocation (Import Shipments) API

Exposes app/modules/purchasing/services/allocation.py's workflow:
create_import_shipment (DRAFT, with LandedCostLine items and a SHA-256
approvable hash per FR-1212) -> allocate_shipment_costs (persists
LandedCostAllocation records across target GoodsReceiptLines via the
Largest Remainder Method) -> post_landed_costs (allocates + posts the
shipment + emits purchase.landed_cost_allocated).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.db.database import get_tenant_db
from app.modules.purchasing.exceptions import (
    ImportShipmentNotFoundError,
    LandedCostAllocationError,
)
from app.modules.purchasing.models.landed_cost import (
    AllocationBasis,
    ImportShipment,
    LandedCostAllocation,
    LandedCostType,
)
from app.modules.purchasing.services.allocation import (
    allocate_shipment_costs,
    create_import_shipment,
    post_landed_costs,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/purchasing/import-shipments", tags=["Purchasing - Landed Cost Allocation"])


class LandedCostLineIn(BaseModel):
    cost_type: LandedCostType
    amount: Decimal
    currency: str | None = None
    fx_rate: Decimal | None = None
    allocation_basis: AllocationBasis = AllocationBasis.VALUE


class ImportShipmentCreateRequest(BaseModel):
    shipment_ref: str
    supplier_ids: list[UUID]
    po_ids: list[UUID]
    currency: str = "EGP"
    fx_rate: Decimal = Decimal("1.0000")
    lines: list[LandedCostLineIn] | None = None


@router.post(
    "",
    response_model=ImportShipment,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT import shipment with landed cost lines (SHA-256 approvable hash per FR-1212)",
)
async def create_shipment(
    data: ImportShipmentCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ImportShipment:
    lines_data: list[dict[str, Any]] = [line.model_dump(exclude_none=True) for line in (data.lines or [])]
    shipment = await create_import_shipment(
        session=session,
        shipment_ref=data.shipment_ref,
        supplier_ids=data.supplier_ids,
        po_ids=data.po_ids,
        currency=data.currency,
        fx_rate=data.fx_rate,
        lines_data=lines_data,
    )
    await session.commit()
    return shipment


@router.get(
    "/{shipment_id}",
    response_model=ImportShipment,
    summary="Get an import shipment by ID (includes landed cost lines)",
)
async def get_shipment(
    shipment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ImportShipment:
    result = await session.execute(
        select(ImportShipment).where(ImportShipment.id == shipment_id).options(selectinload(ImportShipment.lines))
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail=f"Import shipment '{shipment_id}' not found.")
    return shipment


class AllocationOut(BaseModel):
    id: UUID
    landed_cost_line_id: UUID
    target_grn_line_id: UUID
    allocated_amount: Decimal

    class Config:
        from_attributes = True


@router.post(
    "/{shipment_id}/allocate",
    response_model=list[AllocationOut],
    summary="Allocate all landed cost lines across target GRN lines (piastre-exact, Largest Remainder Method)",
)
async def allocate_shipment(
    shipment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> list[AllocationOut]:
    try:
        allocations = await allocate_shipment_costs(session=session, shipment_id=shipment_id)
        await session.commit()
        return [AllocationOut.model_validate(a) for a in allocations]
    except ImportShipmentNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LandedCostAllocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{shipment_id}/post",
    response_model=ImportShipment,
    summary="Post the shipment (allocates + transitions to POSTED/CLEARED, emits purchase.landed_cost_allocated)",
)
async def post_shipment(
    shipment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ImportShipment:
    try:
        shipment = await post_landed_costs(session=session, shipment_id=shipment_id)
        await session.commit()
        return shipment
    except ImportShipmentNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LandedCostAllocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
