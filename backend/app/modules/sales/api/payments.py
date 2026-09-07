"""
app/modules/sales/api/payments.py — Customer (Sales) Payment REST API

Wave 3 item 1. Exposes app/modules/sales/services/payments.py's workflow:
create_sales_payment (DRAFT, optional initial allocations) ->
allocate_sales_payment (allocates against a POSTED sales invoice, rejecting
over-allocation past the invoice's outstanding balance) -> post_sales_payment
(DRAFT -> POSTED, flips fully-covered invoices to PAID, publishes
sales.payment_received for the GL Bridge). Mirrors
app/modules/purchasing/api/payments.py's shape for the Accounts Receivable
side.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.db.database import get_tenant_db
from app.modules.sales.models.payments import SalesPayment, SalesPaymentStatus
from app.modules.sales.services.payments import (
    allocate_sales_payment,
    create_sales_payment,
    post_sales_payment,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/payments", tags=["Sales - Customer Payments"])


class PaymentAllocationIn(BaseModel):
    invoice_id: UUID
    allocated_amount: Decimal


class SalesPaymentCreateRequest(BaseModel):
    contact_id: UUID
    payment_number: str
    amount: Decimal = Decimal("0.0000")
    payment_date: date | None = None
    payment_method: str = "CASH"
    reference: str | None = None
    notes: str | None = None
    currency: str = "EGP"
    treasury_id: UUID | None = None
    allocations: list[PaymentAllocationIn] | None = None


def _http_error_for(exc: ValueError) -> HTTPException:
    detail = str(exc)
    code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=detail)


@router.post(
    "",
    response_model=SalesPayment,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT customer payment, optionally with initial invoice allocations",
)
async def create_payment(
    data: SalesPaymentCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesPayment:
    allocations_data = (
        [a.model_dump() for a in data.allocations] if data.allocations else None
    )
    try:
        payment = await create_sales_payment(
            session=session,
            contact_id=data.contact_id,
            payment_number=data.payment_number,
            amount=data.amount,
            payment_date=data.payment_date,
            payment_method=data.payment_method,
            reference=data.reference,
            notes=data.notes,
            currency=data.currency,
            treasury_id=data.treasury_id,
            created_by=current_user.id,
            allocations_data=allocations_data,
        )
        await session.commit()
        return payment
    except ValueError as exc:
        await session.rollback()
        raise _http_error_for(exc) from exc


@router.get(
    "",
    response_model=list[SalesPayment],
    summary="List customer payments",
)
async def list_payments(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    contact_id: UUID | None = Query(default=None),
    status_filter: SalesPaymentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SalesPayment]:
    q = select(SalesPayment)
    if contact_id:
        q = q.where(SalesPayment.contact_id == contact_id)
    if status_filter:
        q = q.where(SalesPayment.status == status_filter)
    q = q.order_by(SalesPayment.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


@router.get(
    "/{payment_id}",
    response_model=SalesPayment,
    summary="Get a customer payment by ID (includes allocations)",
)
async def get_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesPayment:
    result = await session.execute(
        select(SalesPayment)
        .where(SalesPayment.id == payment_id)
        .options(selectinload(SalesPayment.allocations))
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Customer payment '{payment_id}' not found.")
    return payment


@router.post(
    "/{payment_id}/allocate",
    response_model=SalesPayment,
    summary="Allocate a DRAFT payment against a POSTED sales invoice",
)
async def allocate(
    payment_id: UUID,
    data: PaymentAllocationIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesPayment:
    try:
        payment = await allocate_sales_payment(
            session=session,
            payment_id=payment_id,
            invoice_id=data.invoice_id,
            allocated_amount=data.allocated_amount,
        )
        await session.commit()
        return payment
    except ValueError as exc:
        await session.rollback()
        raise _http_error_for(exc) from exc


@router.post(
    "/{payment_id}/post",
    response_model=SalesPayment,
    summary="Post a DRAFT customer payment (publishes sales.payment_received, may flip invoice(s) to PAID)",
)
async def post_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesPayment:
    try:
        payment = await post_sales_payment(session=session, payment_id=payment_id)
        await session.commit()
        return payment
    except ValueError as exc:
        await session.rollback()
        raise _http_error_for(exc) from exc
