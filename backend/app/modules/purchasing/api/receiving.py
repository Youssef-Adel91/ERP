"""
app/modules/purchasing/api/receiving.py — Goods Receipt (GRN) REST API

Exposes app/modules/purchasing/services/receiving.py's receive_goods, which
enforces the Golden Invariant (FR-522: qty_received <= qty_ordered, 0%
tolerance, raises OverReceiptError) and emits the purchase.goods_received
Outbox event — Bounded Context: this does NOT touch StockLevel/CostLayer
itself, that happens downstream when the event is consumed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.db.database import get_tenant_db
from app.modules.purchasing.exceptions import OverReceiptError, PurchaseOrderNotFoundError
from app.modules.purchasing.models.core import GoodsReceipt
from app.modules.purchasing.services.receiving import receive_goods
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/purchasing/receipts", tags=["Purchasing - Goods Receipts"])


class GoodsReceiptLineIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    qty_received: Decimal
    qty_rejected: Decimal | None = None
    batch_id: UUID | None = None
    serial_ids: list[str] | None = None
    po_line_id: UUID | None = None
    unit_cost_estimated: Decimal | None = None


class GoodsReceiptCreateRequest(BaseModel):
    supplier_id: UUID
    warehouse_id: UUID
    lines: list[GoodsReceiptLineIn]
    po_id: UUID | None = None
    receipt_date: date | None = None
    branch_id: UUID | None = None
    supplier_delivery_ref: str | None = None
    grn_number: str | None = None


@router.post(
    "",
    response_model=GoodsReceipt,
    status_code=status.HTTP_201_CREATED,
    summary="Record an inbound goods receipt (GRN), optionally matched against a PO",
)
async def create_receipt(
    data: GoodsReceiptCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> GoodsReceipt:
    lines_data = [line.model_dump(exclude_none=True) for line in data.lines]
    try:
        grn = await receive_goods(
            session=session,
            supplier_id=data.supplier_id,
            warehouse_id=data.warehouse_id,
            lines_data=lines_data,
            po_id=data.po_id,
            receipt_date=data.receipt_date,
            branch_id=data.branch_id,
            supplier_delivery_ref=data.supplier_delivery_ref,
            grn_number=data.grn_number,
        )
        await session.commit()
        return grn
    except PurchaseOrderNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OverReceiptError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/{grn_id}",
    response_model=GoodsReceipt,
    summary="Get a goods receipt by ID (includes lines)",
)
async def get_receipt(
    grn_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> GoodsReceipt:
    result = await session.execute(
        select(GoodsReceipt).where(GoodsReceipt.id == grn_id).options(selectinload(GoodsReceipt.lines))
    )
    grn = result.scalar_one_or_none()
    if not grn:
        raise HTTPException(status_code=404, detail=f"Goods receipt '{grn_id}' not found.")
    return grn
