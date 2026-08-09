"""
app/modules/inventory/api/stock.py — Stock Management API

NOTE (Phase 1 dedup): originally this router was built against
app/modules/inventory/models/stock.py's ProductBatch/CostLayer pair (tables
inv_product_batches / inv_cost_layers). That pair was a duplicate of the
richer, canonical Batch/CostLayer models in models/core.py (tied into
Item/Warehouse/StockLevel/StockMovement/CostConsumption — the design already
used by services/costing.py's consume_stock()). This router has been migrated
to use the models/core.py pair so there is a single source of truth for cost
layers. See models/stock.py's module docstring for the resolution record.
"""
from datetime import date, datetime, UTC
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.models.core import Batch, CostLayer
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/stock", tags=["stock"])

# ── Schemas ──────────────────────────────────────────────────────────────────

class StockReceiptRequest(BaseModel):
    item_id: UUID
    warehouse_id: UUID
    quantity: Decimal
    unit_cost: Decimal
    variant_id: Optional[UUID] = None
    batch_no: Optional[str] = None
    manufacture_date: Optional[date] = None
    expiry_date: Optional[date] = None


class CostLayerResponse(BaseModel):
    id: UUID
    item_id: UUID
    variant_id: Optional[UUID] = None
    batch_id: Optional[UUID] = None
    warehouse_id: UUID
    qty_received: Decimal
    qty_remaining: Decimal
    unit_cost_original: Decimal
    unit_cost_current: Decimal
    received_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ItemValuationResponse(BaseModel):
    item_id: UUID
    total_qty: Decimal
    total_value: Decimal


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/receipt",
    response_model=CostLayerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a stock receipt (creates CostLayer)",
)
async def register_stock_receipt(
    data: StockReceiptRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> CostLayerResponse:
    batch_id = None

    # Handle optional batch creation
    if data.batch_no:
        result = await db.execute(
            select(Batch)
            .where(
                Batch.item_id == data.item_id,
                Batch.batch_no == data.batch_no,
            )
        )
        batch = result.scalar_one_or_none()

        if not batch:
            batch = Batch(
                item_id=data.item_id,
                variant_id=data.variant_id,
                batch_no=data.batch_no,
                manufacture_date=data.manufacture_date,
                expiry_date=data.expiry_date,
            )
            db.add(batch)
            await db.flush()  # To get the batch ID
        batch_id = batch.id

    # Create Cost Layer
    layer = CostLayer(
        item_id=data.item_id,
        variant_id=data.variant_id,
        warehouse_id=data.warehouse_id,
        batch_id=batch_id,
        qty_received=data.quantity,
        qty_remaining=data.quantity,
        unit_cost_original=data.unit_cost,
        unit_cost_current=data.unit_cost,
        received_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(layer)
    await db.commit()
    await db.refresh(layer)

    return CostLayerResponse.model_validate(layer)


@router.get(
    "/valuation/{item_id}",
    response_model=ItemValuationResponse,
    summary="Get current item valuation based on active cost layers",
)
async def get_item_valuation(
    item_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ItemValuationResponse:
    result = await db.execute(
        select(CostLayer)
        .where(
            CostLayer.item_id == item_id,
            CostLayer.qty_remaining > 0,
        )
    )
    layers = result.scalars().all()

    total_qty = sum((layer.qty_remaining for layer in layers), Decimal("0"))
    total_value = sum(
        (layer.qty_remaining * layer.unit_cost_current for layer in layers), Decimal("0")
    )

    return ItemValuationResponse(
        item_id=item_id,
        total_qty=total_qty,
        total_value=total_value,
    )
