"""
app/modules/purchasing/api/payments.py — Supplier Payment REST API

Exposes app/modules/purchasing/services/payments.py's full workflow:
create_supplier_payment (DRAFT, optional initial allocations) ->
allocate_payment (allocates against a POSTED VendorBill, computing realized
FX gain/loss per FR-533) -> post_supplier_payment (DRAFT -> POSTED, emits
purchase.payment_made).
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
from app.modules.purchasing.exceptions import (
    PaymentAllocationError,
    SupplierPaymentNotFoundError,
    VendorBillNotFoundError,
)
from app.modules.purchasing.models.payments import SupplierPayment
from app.modules.purchasing.services.payments import (
    allocate_payment,
    create_supplier_payment,
    post_supplier_payment,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/purchasing/payments", tags=["Purchasing - Supplier Payments"])


class PaymentAllocationIn(BaseModel):
    bill_id: UUID
    allocated_amount: Decimal


class SupplierPaymentCreateRequest(BaseModel):
    supplier_id: UUID
    treasury_id: UUID
    payment_number: str
    amount: Decimal = Decimal("0.0000")
    payment_date: date | None = None
    currency: str = "EGP"
    fx_rate: Decimal = Decimal("1.000000")
    allocations: list[PaymentAllocationIn] | None = None


@router.post(
    "",
    response_model=SupplierPayment,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT supplier payment, optionally with initial bill allocations",
)
async def create_payment(
    data: SupplierPaymentCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SupplierPayment:
    allocations_data = (
        [a.model_dump() for a in data.allocations] if data.allocations else None
    )
    try:
        payment = await create_supplier_payment(
            session=session,
            supplier_id=data.supplier_id,
            treasury_id=data.treasury_id,
            payment_number=data.payment_number,
            amount=data.amount,
            payment_date=data.payment_date,
            currency=data.currency,
            fx_rate=data.fx_rate,
            allocations_data=allocations_data,
        )
        await session.commit()
        return payment
    except (VendorBillNotFoundError, SupplierPaymentNotFoundError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PaymentAllocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/{payment_id}",
    response_model=SupplierPayment,
    summary="Get a supplier payment by ID (includes allocations)",
)
async def get_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SupplierPayment:
    result = await session.execute(
        select(SupplierPayment)
        .where(SupplierPayment.id == payment_id)
        .options(selectinload(SupplierPayment.allocations))
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Supplier payment '{payment_id}' not found.")
    return payment


@router.post(
    "/{payment_id}/allocate",
    response_model=SupplierPayment,
    summary="Allocate a DRAFT payment against a POSTED vendor bill (computes realized FX gain/loss)",
)
async def allocate(
    payment_id: UUID,
    data: PaymentAllocationIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SupplierPayment:
    try:
        payment = await allocate_payment(
            session=session,
            payment_id=payment_id,
            bill_id=data.bill_id,
            allocated_amount=data.allocated_amount,
        )
        await session.commit()
        return payment
    except (VendorBillNotFoundError, SupplierPaymentNotFoundError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PaymentAllocationError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{payment_id}/post",
    response_model=SupplierPayment,
    summary="Post a DRAFT supplier payment to AP/Treasury (publishes purchase.payment_made)",
)
async def post_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SupplierPayment:
    try:
        payment = await post_supplier_payment(session=session, payment_id=payment_id)
        await session.commit()
        return payment
    except SupplierPaymentNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
