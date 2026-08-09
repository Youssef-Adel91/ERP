"""
app/modules/inventory/api/transfer.py — Inter-Warehouse Stock Transfer API

Exposes app/modules/inventory/services/transfer.py's workflow
(dispatch_transfer, receive_transfer) as thin HTTP endpoints. There is no
dedicated "create a StockTransfer" service function (dispatch_transfer
expects a DRAFT StockTransfer + StockTransferLine rows to already exist),
so this router adds a minimal direct creation endpoint for the transfer
header + lines — same convention as stock_take.py's create endpoint —
while dispatch/receive call the real service functions that own the
costing/StockLevel side effects.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.db.database import get_tenant_db
from app.modules.inventory.models.transfer import StockTransfer, StockTransferLine
from app.modules.inventory.services.transfer import (
    ReceiptLine,
    dispatch_transfer,
    receive_transfer,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/inventory/transfers", tags=["Inventory - Transfers"])


class TransferLineIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    qty_dispatched: Decimal


class TransferCreateRequest(BaseModel):
    transfer_number: str
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    transit_warehouse_id: UUID
    lines: list[TransferLineIn]


@router.post(
    "",
    response_model=StockTransfer,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new DRAFT stock transfer with lines",
)
async def create_transfer(
    data: TransferCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTransfer:
    if not data.lines:
        raise HTTPException(status_code=422, detail="Transfer must contain at least one line")

    transfer = StockTransfer(
        transfer_number=data.transfer_number,
        source_warehouse_id=data.source_warehouse_id,
        destination_warehouse_id=data.destination_warehouse_id,
        transit_warehouse_id=data.transit_warehouse_id,
    )
    session.add(transfer)
    await session.flush()

    for line_in in data.lines:
        session.add(
            StockTransferLine(
                transfer_id=transfer.id,
                item_id=line_in.item_id,
                variant_id=line_in.variant_id,
                batch_id=line_in.batch_id,
                serial_id=line_in.serial_id,
                qty_dispatched=line_in.qty_dispatched,
            )
        )

    await session.commit()
    await session.refresh(transfer)
    return transfer


@router.get(
    "/{transfer_id}",
    response_model=StockTransfer,
    summary="Get a stock transfer by ID",
)
async def get_transfer(
    transfer_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTransfer:
    transfer = await session.get(StockTransfer, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail=f"StockTransfer '{transfer_id}' not found.")
    return transfer


@router.post(
    "/{transfer_id}/dispatch",
    response_model=StockTransfer,
    summary="Dispatch a DRAFT transfer (source -> transit warehouse), carrying over exact blended cost",
)
async def dispatch_transfer_endpoint(
    transfer_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTransfer:
    try:
        transfer = await dispatch_transfer(session, transfer_id)
        await session.commit()
        await session.refresh(transfer)
        return transfer
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc


class ReceiptLineIn(BaseModel):
    line_id: UUID
    qty_received: Decimal


class ReceiveTransferRequest(BaseModel):
    receipt_lines: list[ReceiptLineIn]


@router.post(
    "/{transfer_id}/receive",
    response_model=StockTransfer,
    summary="Receive an IN_TRANSIT (or PARTIALLY_RECEIVED) transfer at the destination warehouse",
)
async def receive_transfer_endpoint(
    transfer_id: UUID,
    data: ReceiveTransferRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> StockTransfer:
    receipt_lines = [ReceiptLine(line_id=rl.line_id, qty_received=rl.qty_received) for rl in data.receipt_lines]
    try:
        transfer = await receive_transfer(session, transfer_id, receipt_lines)
        await session.commit()
        await session.refresh(transfer)
        return transfer
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc
