"""
app/modules/purchasing/api/orders.py — Purchase Order REST API

Exposes app/modules/purchasing/services/orders.py (create_purchase_order,
confirm_purchase_order) — the PurchaseOrder document itself, a distinct
concern from VendorBill (already wired via api/bills.py) and from
GoodsReceipt (wired via api/receiving.py in this same batch).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.database import get_redis, get_tenant_db
from app.core.idempotency import IdempotencyKey, get_cached_resource_id, store_idempotent_result
from app.modules.purchasing.exceptions import (
    InvalidPOStateError,
    PurchaseOrderNotFoundError,
    SupplierNotFoundError,
)
from app.modules.purchasing.models.core import PurchaseOrder, PurchaseOrderStatus
from app.modules.purchasing.services.orders import confirm_purchase_order, create_purchase_order
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/purchasing/orders", tags=["Purchasing - Purchase Orders"])


class PurchaseOrderLineIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    qty_ordered: Decimal
    unit_price: Decimal
    expected_landed_unit_cost: Decimal | None = None


class PurchaseOrderCreateRequest(BaseModel):
    supplier_id: UUID
    warehouse_id: UUID
    lines: list[PurchaseOrderLineIn]
    order_date: date | None = None
    expected_date: date | None = None
    currency: str = "EGP"
    fx_rate: Decimal = Decimal("1.0000")
    branch_id: UUID | None = None
    po_number: str | None = None


@router.post(
    "",
    response_model=PurchaseOrder,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT purchase order",
)
async def create_order(
    data: PurchaseOrderCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    redis: aioredis.Redis = Depends(get_redis),
    idempotency_key: str | None = IdempotencyKey,
) -> PurchaseOrder:
    # Idempotency: a client-supplied Idempotency-Key header lets a retried
    # (e.g. network-retried or double-clicked) request return the PO
    # already created by the first attempt instead of creating a duplicate.
    cached_id = await get_cached_resource_id(
        redis,
        tenant_id=current_user.tenant_id,
        endpoint="purchasing.orders.create",
        idempotency_key=idempotency_key,
    )
    if cached_id is not None:
        existing = await session.get(PurchaseOrder, cached_id)
        if existing is not None:
            return existing

    lines_data = [line.model_dump(exclude_none=True) for line in data.lines]
    try:
        po = await create_purchase_order(
            session=session,
            supplier_id=data.supplier_id,
            warehouse_id=data.warehouse_id,
            lines_data=lines_data,
            order_date=data.order_date,
            expected_date=data.expected_date,
            currency=data.currency,
            fx_rate=data.fx_rate,
            branch_id=data.branch_id,
            po_number=data.po_number,
        )
        await session.commit()
        await store_idempotent_result(
            redis,
            tenant_id=current_user.tenant_id,
            endpoint="purchasing.orders.create",
            idempotency_key=idempotency_key,
            resource_id=po.id,
        )
        return po
    except SupplierNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "",
    response_model=list[PurchaseOrder],
    summary="List purchase orders",
)
async def list_orders(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    status_filter: PurchaseOrderStatus | None = Query(default=None, alias="status"),
    supplier_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PurchaseOrder]:
    q = select(PurchaseOrder)
    if status_filter:
        q = q.where(PurchaseOrder.status == status_filter)
    if supplier_id:
        q = q.where(PurchaseOrder.supplier_id == supplier_id)
    q = q.order_by(PurchaseOrder.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(q)
    return list(result.scalars().all())


@router.get(
    "/{po_id}",
    response_model=PurchaseOrder,
    summary="Get a purchase order by ID (includes lines)",
)
async def get_order(
    po_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> PurchaseOrder:
    result = await session.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == po_id).options(selectinload(PurchaseOrder.lines))
    )
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail=f"Purchase order '{po_id}' not found.")
    return po


@router.post(
    "/{po_id}/confirm",
    response_model=PurchaseOrder,
    summary="Confirm a purchase order (DRAFT/CONFIRMED -> CONFIRMED, state -> APPROVED)",
    description=(
        "Confirms the PO — unless an active Approval Rule matches it (e.g. "
        "total_amount over a configured threshold), in which case this call "
        "instead submits it for approval (`state` -> `PENDING_APPROVAL`) and "
        "returns without confirming. Call this endpoint again after the "
        "request is approved via `POST /approvals/requests/{id}/decide` to "
        "actually confirm it. Tenants with no configured Approval Rules for "
        "`purchase_order` are unaffected — this always confirms immediately."
    ),
)
async def confirm_order(
    po_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> PurchaseOrder:
    try:
        po = await confirm_purchase_order(session=session, po_id=po_id, requested_by=current_user.id)
        await session.commit()
        return po
    except PurchaseOrderNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidPOStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
