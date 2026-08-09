"""
app/modules/inventory/api/stock_take.py — Physical Stock Count (Stock Take) API

Exposes app/modules/inventory/services/stock_take.py's workflow
(start_count -> get_blind_count_sheet -> record_count -> post_stock_take)
as thin HTTP endpoints. There is no dedicated "create a StockTake" service
function in stock_take.py (the DRAFT StockTake row is expected to already
exist before start_count is called), so this router adds a minimal direct
creation endpoint for the StockTake header — mirroring the same
"simple CRUD may be inline" convention already used by items.py/stock.py
for Item/Warehouse/CostLayer creation — while every state-transition
endpoint below calls the real service functions.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.models.stock_take import StockTake
from app.modules.inventory.services.stock_take import (
    get_blind_count_sheet,
    post_stock_take,
    record_count,
    start_count,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/inventory/stock-takes", tags=["Inventory - Stock Take"])


class StockTakeCreateRequest(BaseModel):
    warehouse_id: UUID
    reference_id: str | None = None


@router.post(
    "",
    response_model=StockTake,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new DRAFT stock take for a warehouse",
)
async def create_stock_take(
    data: StockTakeCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTake:
    stock_take = StockTake(warehouse_id=data.warehouse_id, reference_id=data.reference_id)
    session.add(stock_take)
    await session.commit()
    await session.refresh(stock_take)
    return stock_take


@router.get(
    "/{stock_take_id}",
    response_model=StockTake,
    summary="Get a stock take by ID",
)
async def get_stock_take(
    stock_take_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTake:
    stock_take = await session.get(StockTake, stock_take_id)
    if not stock_take:
        raise HTTPException(status_code=404, detail=f"StockTake '{stock_take_id}' not found.")
    return stock_take


@router.post(
    "/{stock_take_id}/start",
    response_model=StockTake,
    summary="Start the count (DRAFT -> COUNTING), snapshots current StockLevels into lines",
)
async def start_stock_take(
    stock_take_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTake:
    try:
        stock_take = await start_count(session, stock_take_id)
        await session.commit()
        await session.refresh(stock_take)
        return stock_take
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc


class CountSheetLine(BaseModel):
    line_id: UUID
    item_id: UUID
    variant_id: UUID | None = None
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    expected_qty: Decimal | None = None
    counted_qty: Decimal | None = None


@router.get(
    "/{stock_take_id}/count-sheet",
    response_model=list[CountSheetLine],
    summary="Get the blind count sheet for a stock take (expected_qty masked)",
)
async def get_count_sheet(
    stock_take_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> list[CountSheetLine]:
    sheet = await get_blind_count_sheet(session, stock_take_id)
    return [CountSheetLine(**row) for row in sheet]


class CountEntry(BaseModel):
    line_id: UUID | None = None
    item_id: UUID | None = None
    variant_id: UUID | None = None
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    counted_qty: Decimal


class RecordCountsRequest(BaseModel):
    counts: list[CountEntry]


@router.post(
    "/{stock_take_id}/counts",
    response_model=StockTake,
    summary="Record physical counts against a stock take's lines (moves to REVIEW)",
)
async def record_stock_take_counts(
    stock_take_id: UUID,
    data: RecordCountsRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTake:
    counts_payload = [c.model_dump(exclude_none=True) for c in data.counts]
    try:
        await record_count(session, stock_take_id, counts_payload)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    stock_take = await session.get(StockTake, stock_take_id)
    if not stock_take:
        raise HTTPException(status_code=404, detail=f"StockTake '{stock_take_id}' not found.")
    return stock_take


@router.post(
    "/{stock_take_id}/post",
    response_model=StockTake,
    summary="Post the stock take (resolves variances via the Costing Engine, emits inventory.stock_take_posted)",
)
async def post_stock_take_endpoint(
    stock_take_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTake:
    try:
        stock_take = await post_stock_take(session, stock_take_id)
        await session.commit()
        await session.refresh(stock_take)
        return stock_take
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
