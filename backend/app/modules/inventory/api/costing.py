"""
app/modules/inventory/api/costing.py — Costing Engine API

Exposes app/modules/inventory/services/costing.py's consume_stock (FIFO/WAC
cost-layer consumption engine, used internally by fulfillment/transfer/
stock-take flows) and consume_stock_fifo (single-item FIFO consumption
helper) as thin HTTP endpoints, for callers that need to drive the costing
engine directly (e.g. manual stock issues / write-offs / integration jobs)
rather than through a higher-level workflow (sales fulfillment, transfers,
stock takes) that already calls it internally.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.exceptions import InsufficientStockError
from app.modules.inventory.services.costing import (
    CostingRequest,
    consume_stock,
    consume_stock_fifo,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/inventory/costing", tags=["Inventory - Costing"])


class CostingRequestIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    warehouse_id: UUID
    quantity: Decimal
    movement_type: str
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    uom_id: UUID | None = None
    reference_id: str | None = None
    contact_id: UUID | None = None


class ConsumeStockRequest(BaseModel):
    requests: list[CostingRequestIn]


class MovementOut(BaseModel):
    id: UUID
    item_id: UUID
    variant_id: UUID | None = None
    warehouse_id: UUID
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    qty: Decimal
    movement_type: str
    reference_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConsumptionOut(BaseModel):
    id: UUID
    layer_id: UUID
    movement_id: UUID
    qty_consumed: Decimal
    unit_cost_at_consumption: Decimal

    model_config = ConfigDict(from_attributes=True)


class ConsumeStockResponse(BaseModel):
    movements: list[MovementOut]
    consumptions: list[ConsumptionOut]


@router.post(
    "/consume",
    response_model=ConsumeStockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Consume stock against open cost layers (FIFO/WAC) for one or more lines",
)
async def consume_stock_endpoint(
    data: ConsumeStockRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ConsumeStockResponse:
    if not data.requests:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="requests cannot be empty")

    reqs = [CostingRequest(**item.model_dump()) for item in data.requests]
    try:
        movements, consumptions = await consume_stock(session, reqs)
        await session.commit()
    except InsufficientStockError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return ConsumeStockResponse(
        movements=[MovementOut.model_validate(m) for m in movements],
        consumptions=[ConsumptionOut.model_validate(c) for c in consumptions],
    )


class ConsumeFifoRequest(BaseModel):
    item_id: UUID
    warehouse_id: UUID
    qty_to_consume: Decimal


class ConsumedLayerOut(BaseModel):
    layer_id: UUID
    qty_consumed: Decimal


@router.post(
    "/consume-fifo",
    response_model=list[ConsumedLayerOut],
    summary="Consume stock for a single item/warehouse using strict FIFO layer order",
)
async def consume_stock_fifo_endpoint(
    data: ConsumeFifoRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> list[ConsumedLayerOut]:
    try:
        consumed = await consume_stock_fifo(
            session=session,
            item_id=data.item_id,
            warehouse_id=data.warehouse_id,
            qty_to_consume=data.qty_to_consume,
        )
        await session.commit()
    except InsufficientStockError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return [ConsumedLayerOut(layer_id=layer.id, qty_consumed=qty) for layer, qty in consumed]
