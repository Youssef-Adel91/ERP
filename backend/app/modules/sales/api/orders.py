"""
app/modules/sales/api/orders.py — Sales Order REST API

Exposes app/modules/sales/services/orders.py (create_sales_order,
confirm_sales_order) — the SalesOrder document itself, a distinct concern
from SalesInvoice (already wired via api/invoices.py). create_sales_order
prices unpriced lines via the Inventory pricing interface; confirm_sales_order
reserves stock for every line via the Inventory reservation interface
(propagating InsufficientStockError as 409).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.database import get_tenant_db
from app.modules.inventory.exceptions import InsufficientStockError
from app.modules.sales.models.core import SalesOrder, SalesOrderStatus
from app.modules.sales.services.orders import confirm_sales_order, create_sales_order
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/orders", tags=["Sales - Orders"])


class SalesOrderLineIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    uom_id: UUID | None = None
    qty: Decimal
    unit_price: Decimal | None = None


class SalesOrderCreateRequest(BaseModel):
    contact_id: UUID
    lines: list[SalesOrderLineIn]
    order_date: date | None = None
    currency: str = "EGP"
    price_list_id: UUID | None = None
    order_number: str | None = None


@router.post(
    "",
    response_model=SalesOrder,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT sales order (unpriced lines are priced via the Inventory pricing interface)",
)
async def create_order(
    data: SalesOrderCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesOrder:
    lines_data = [line.model_dump(exclude_none=True) for line in data.lines]
    try:
        order = await create_sales_order(
            session=session,
            contact_id=data.contact_id,
            lines_data=lines_data,
            order_date=data.order_date,
            currency=data.currency,
            price_list_id=data.price_list_id,
            order_number=data.order_number,
        )
        await session.commit()
        return order
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "",
    response_model=list[SalesOrder],
    summary="List sales orders",
)
async def list_orders(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    status_filter: SalesOrderStatus | None = Query(default=None, alias="status"),
    contact_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SalesOrder]:
    q = select(SalesOrder)
    if status_filter:
        q = q.where(SalesOrder.status == status_filter)
    if contact_id:
        q = q.where(SalesOrder.contact_id == contact_id)
    q = q.order_by(SalesOrder.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(q)
    return list(result.scalars().all())


@router.get(
    "/{order_id}",
    response_model=SalesOrder,
    summary="Get a sales order by ID (includes lines)",
)
async def get_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesOrder:
    result = await session.execute(
        select(SalesOrder).where(SalesOrder.id == order_id).options(selectinload(SalesOrder.lines))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail=f"Sales order '{order_id}' not found.")
    return order


class ConfirmOrderRequest(BaseModel):
    warehouse_id: UUID


@router.post(
    "/{order_id}/confirm",
    response_model=SalesOrder,
    summary="Confirm a DRAFT sales order (DRAFT -> CONFIRMED, reserves stock for every line)",
)
async def confirm_order(
    order_id: UUID,
    data: ConfirmOrderRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesOrder:
    try:
        order = await confirm_sales_order(session=session, order_id=order_id, warehouse_id=data.warehouse_id)
        await session.commit()
        return order
    except InsufficientStockError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc
