"""
app/modules/inventory/api/reservation.py — Stock Reservation API

Exposes app/modules/inventory/services/reservation.py's reserve_stock and
release_reservation (FR-360) as thin HTTP endpoints. These are normally
called internally by sales order confirmation/fulfillment, but are exposed
directly here for manual/administrative reservation management and for
other verticals (e.g. service bookings) that need to hold stock without a
full SalesOrder lifecycle.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.exceptions import InsufficientStockError
from app.modules.inventory.services.reservation import (
    release_reservation,
    reserve_stock,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/inventory/reservations", tags=["Inventory - Reservations"])


class ReserveStockRequest(BaseModel):
    item_id: UUID
    warehouse_id: UUID
    qty: Decimal
    source_doc_id: str | None = None
    variant_id: UUID | None = None
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    uom_id: UUID | None = None


class ReleaseReservationRequest(BaseModel):
    item_id: UUID
    warehouse_id: UUID
    qty: Decimal
    variant_id: UUID | None = None
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    uom_id: UUID | None = None


class ReservationActionResponse(BaseModel):
    success: bool


@router.post(
    "/reserve",
    response_model=ReservationActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Reserve stock for an order (increments qty_reserved on StockLevel)",
)
async def reserve_stock_endpoint(
    data: ReserveStockRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ReservationActionResponse:
    try:
        ok = await reserve_stock(
            session=session,
            item_id=data.item_id,
            warehouse_id=data.warehouse_id,
            qty=data.qty,
            source_doc_id=data.source_doc_id,
            variant_id=data.variant_id,
            batch_id=data.batch_id,
            serial_id=data.serial_id,
            uom_id=data.uom_id,
        )
        await session.commit()
    except InsufficientStockError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return ReservationActionResponse(success=ok)


@router.post(
    "/release",
    response_model=ReservationActionResponse,
    summary="Release a prior stock reservation (decrements qty_reserved on StockLevel)",
)
async def release_reservation_endpoint(
    data: ReleaseReservationRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ReservationActionResponse:
    try:
        await release_reservation(
            session=session,
            item_id=data.item_id,
            warehouse_id=data.warehouse_id,
            qty=data.qty,
            variant_id=data.variant_id,
            batch_id=data.batch_id,
            serial_id=data.serial_id,
            uom_id=data.uom_id,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "non-existent" in detail.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=detail) from exc

    return ReservationActionResponse(success=True)
