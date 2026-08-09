"""
app/modules/sales/api/returns.py — Sales Return (RMA) REST API

Exposes app/modules/sales/services/returns.py's full RMA workflow:
create_sales_return (DRAFT, linked to an original SalesInvoice) ->
process_sales_return (validates serial ownership fraud-check, reverses the
exact historical unit cost into an inbound CostLayer/StockMovement,
transitions returned serials to RETURNED) -> post_credit_note (emits a
negative-total SalesInvoice as the credit note and publishes
sales.credit_note_posted).
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
from app.modules.sales.models.returns import SalesReturn
from app.modules.sales.services.returns import (
    create_sales_return,
    post_credit_note,
    process_sales_return,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/returns", tags=["Sales - Returns"])


class SalesReturnLineIn(BaseModel):
    original_invoice_line_id: UUID
    item_id: UUID
    variant_id: UUID | None = None
    uom_id: UUID | None = None
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    qty: Decimal
    unit_price: Decimal
    tax_rate: Decimal | None = None


class SalesReturnCreateRequest(BaseModel):
    invoice_id: UUID
    contact_id: UUID
    lines: list[SalesReturnLineIn]
    order_id: UUID | None = None


@router.post(
    "",
    response_model=SalesReturn,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT sales return (RMA) linked to an original sales invoice",
)
async def create_return(
    data: SalesReturnCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesReturn:
    lines_data = [line.model_dump(exclude_none=True) for line in data.lines]
    try:
        sales_return = await create_sales_return(
            session=session,
            invoice_id=data.invoice_id,
            contact_id=data.contact_id,
            lines_data=lines_data,
            order_id=data.order_id,
        )
        await session.commit()
        return sales_return
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get(
    "/{return_id}",
    response_model=SalesReturn,
    summary="Get a sales return by ID (includes lines)",
)
async def get_return(
    return_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesReturn:
    result = await session.execute(
        select(SalesReturn).where(SalesReturn.id == return_id).options(selectinload(SalesReturn.lines))
    )
    sales_return = result.scalar_one_or_none()
    if not sales_return:
        raise HTTPException(status_code=404, detail=f"Sales return '{return_id}' not found.")
    return sales_return


class ProcessReturnRequest(BaseModel):
    warehouse_id: UUID


@router.post(
    "/{return_id}/process",
    response_model=SalesReturn,
    summary="Process a DRAFT return (fraud check, exact cost reversal into stock, serial -> RETURNED)",
)
async def process_return(
    return_id: UUID,
    data: ProcessReturnRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesReturn:
    try:
        sales_return = await process_sales_return(session=session, return_id=return_id, warehouse_id=data.warehouse_id)
        await session.commit()
        return sales_return
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post(
    "/{return_id}/credit-note",
    response_model=SalesReturn,
    summary="Post a credit note for a RECEIVED return (RECEIVED -> CREDITED, publishes sales.credit_note_posted)",
)
async def credit_note(
    return_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesReturn:
    try:
        sales_return = await post_credit_note(session=session, return_id=return_id)
        await session.commit()
        return sales_return
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc
