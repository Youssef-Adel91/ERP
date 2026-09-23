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
from decimal import Decimal

from app.modules.inventory.models.core import (
    CostingMethod,
    Item,
    ItemVariant,
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
    # Bug fix (live-reproduced, 20 Sep 2026): the "new item" form had no
    # price field at all, because price lives on ItemVariant, not Item, and
    # nothing ever created a default variant. That silently made every new
    # item unsellable: POS's /pos/catalog does an INNER JOIN against
    # ItemVariant and (by design, see its docstring) omits any item with no
    # variant, so items created here never appeared in the POS product
    # search, with no explanation shown to the user. Accepting an optional
    # price here and creating a matching default ItemVariant (same sku/name
    # as the item) closes that gap for the common single-variant case,
    # without touching the multi-variant path for items that need one.
    price: Decimal | None = None


class ItemResponse(BaseModel):
    id: UUID
    sku: str
    name: str
    egs_code: str | None
    costing_method: CostingMethod
    requires_batch: bool
    requires_serial: bool
    price: Decimal | None = None


@router.post(
    "/items",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new item (product/SKU)",
)
async def create_item(
    data: ItemCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ItemResponse:
    existing = await db.execute(select(Item).where(Item.sku == data.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with SKU '{data.sku}' already exists.",
        )

    try:
        item_fields = data.model_dump(exclude={"price"})
        item = Item(**item_fields)
        db.add(item)
        await db.flush()

        if data.price is not None:
            variant = ItemVariant(
                item_id=item.id,
                name=item.name,
                sku=item.sku,
                price=data.price,
            )
            db.add(variant)

        await db.commit()
        await db.refresh(item)
        return ItemResponse(**item.model_dump(), price=data.price)
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
