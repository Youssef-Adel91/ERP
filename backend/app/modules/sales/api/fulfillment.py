"""
app/modules/sales/api/fulfillment.py — Sales Order Fulfillment API

Exposes app/modules/sales/services/fulfillment.py's fulfill_sales_order,
which for a CONFIRMED/PARTIALLY_FULFILLED SalesOrder: releases the line's
stock reservation, consumes stock via the Inventory Costing Engine
(movement_type=SALES_ISSUE), transitions any serialized line to SOLD, and
advances the SalesOrder to FULFILLED/PARTIALLY_FULFILLED.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.exceptions import InsufficientStockError
from app.modules.sales.models.core import SalesOrder
from app.modules.sales.services.fulfillment import fulfill_sales_order
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/orders", tags=["Sales - Fulfillment"])


class FulfillmentLineIn(BaseModel):
    line_id: UUID | None = None
    item_id: UUID | None = None
    variant_id: UUID | None = None
    qty: Decimal
    serial_id: UUID | None = None
    batch_id: UUID | None = None
    uom_id: UUID | None = None


class FulfillOrderRequest(BaseModel):
    warehouse_id: UUID
    fulfillment_lines: list[FulfillmentLineIn]


class MovementOut(BaseModel):
    id: UUID
    item_id: UUID
    qty: Decimal
    movement_type: str

    model_config = ConfigDict(from_attributes=True)


class FulfillOrderResponse(BaseModel):
    order: SalesOrder
    movement_count: int
    consumption_count: int


@router.post(
    "/{order_id}/fulfill",
    response_model=FulfillOrderResponse,
    summary="Fulfill a CONFIRMED/PARTIALLY_FULFILLED sales order (consumes stock, ships serialized items)",
)
async def fulfill_order(
    order_id: UUID,
    data: FulfillOrderRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> FulfillOrderResponse:
    fulfillment_lines = [fl.model_dump(exclude_none=True) for fl in data.fulfillment_lines]
    try:
        result = await fulfill_sales_order(
            session=session,
            order_id=order_id,
            warehouse_id=data.warehouse_id,
            fulfillment_lines=fulfillment_lines,
        )
        await session.commit()
        await session.refresh(result.order)
        return FulfillOrderResponse(
            order=result.order,
            movement_count=len(result.movements),
            consumption_count=len(result.consumptions),
        )
    except InsufficientStockError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=detail) from exc
