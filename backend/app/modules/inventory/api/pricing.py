"""
app/modules/inventory/api/pricing.py — Price List Resolution API

Exposes app/modules/inventory/services/pricing.py's get_item_price (price
list rule resolution with quantity breaks, UoM conversion, and ItemVariant
price fallback) as a read-only lookup endpoint.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.services.pricing import get_item_price
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/inventory/pricing", tags=["Inventory - Pricing"])


class ItemPriceResponse(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    price_list_id: UUID | None = None
    qty: Decimal
    unit_price: Decimal


@router.get(
    "/price",
    response_model=ItemPriceResponse,
    summary="Resolve the unit price for an item (or variant) at a given quantity/UoM",
)
async def get_price(
    current_user: CurrentUser,
    item_id: UUID = Query(...),
    session: AsyncSession = Depends(get_tenant_db),
    price_list_id: UUID | None = Query(default=None),
    variant_id: UUID | None = Query(default=None),
    qty: Decimal = Query(default=Decimal("1.0")),
    uom_id: UUID | None = Query(default=None),
) -> ItemPriceResponse:
    unit_price = await get_item_price(
        session=session,
        item_id=item_id,
        price_list_id=price_list_id,
        variant_id=variant_id,
        qty=qty,
        uom_id=uom_id,
    )
    return ItemPriceResponse(
        item_id=item_id,
        variant_id=variant_id,
        price_list_id=price_list_id,
        qty=qty,
        unit_price=unit_price,
    )
