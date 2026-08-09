"""
app/modules/inventory/api/items.py — Item & Warehouse Master Data API

Mirrors the user-facing contract of the currently-live app/plugins/inventory
router's `/items` endpoints (create/list/get, search + active-ish filtering)
as closely as models/core.py's leaner Item model allows. Differences from the
live plugin contract, noted explicitly rather than guessed silently:
  - models/core.py's Item has no name_ar / description / category / price /
    cost / quantity_on_hand / reorder_level / is_active columns — it only has
    sku, name, egs_code, costing_method, requires_batch, requires_serial.
    Pricing lives on ItemVariant, stock quantity lives in StockLevel, and
    there is no soft-active flag, so `list_items`'s "active filter" from the
    live plugin has no equivalent column here and is intentionally omitted;
    a `search` filter (sku/name, matching the live plugin's ergonomics) is
    provided instead.
  - Warehouse here also has no soft-active flag; `type` is exposed as a
    filter instead since that's the closest analogous discriminator.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.models.core import (
    CostingMethod,
    Item,
    Warehouse,
    WarehouseType,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(tags=["Inventory - Items"])


# ── Items ─────────────────────────────────────────────────────────────────────


class ItemCreateRequest(BaseModel):
    sku: str
    name: str
    egs_code: str | None = None
    costing_method: CostingMethod = CostingMethod.FIFO
    requires_batch: bool = False
    requires_serial: bool = False


@router.post(
    "/items",
    response_model=Item,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new item (product/SKU)",
)
async def create_item(
    data: ItemCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> Item:
    existing = await db.execute(select(Item).where(Item.sku == data.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with SKU '{data.sku}' already exists.",
        )

    try:
        item = Item(**data.model_dump())
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/items",
    response_model=list[Item],
    summary="List items (optionally search by SKU/name)",
)
async def list_items(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    search: str | None = Query(default=None, description="Match against SKU or name"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Item]:
    q = select(Item)
    if search:
        like = f"%{search}%"
        q = q.where(or_(Item.sku.ilike(like), Item.name.ilike(like)))
    q = q.order_by(Item.name).limit(limit).offset(offset)

    result = await db.execute(q)
    return list(result.scalars().all())


@router.get(
    "/items/{item_id}",
    response_model=Item,
    summary="Get item by ID",
)
async def get_item(
    item_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> Item:
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found.")
    return item


# ── Warehouses ────────────────────────────────────────────────────────────────


class WarehouseCreateRequest(BaseModel):
    name: str
    code: str
    type: WarehouseType = WarehouseType.MAIN


@router.post(
    "/warehouses",
    response_model=Warehouse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new warehouse",
)
async def create_warehouse(
    data: WarehouseCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> Warehouse:
    existing = await db.execute(select(Warehouse).where(Warehouse.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A warehouse with code '{data.code}' already exists.",
        )

    try:
        warehouse = Warehouse(**data.model_dump())
        db.add(warehouse)
        await db.commit()
        await db.refresh(warehouse)
        return warehouse
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/warehouses",
    response_model=list[Warehouse],
    summary="List warehouses",
)
async def list_warehouses(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    type: WarehouseType | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Warehouse]:
    q = select(Warehouse)
    if type:
        q = q.where(Warehouse.type == type)
    q = q.order_by(Warehouse.name).limit(limit).offset(offset)

    result = await db.execute(q)
    return list(result.scalars().all())
