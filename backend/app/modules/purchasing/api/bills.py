"""
app/modules/purchasing/api/bills.py — Vendor Bill REST API

The modules/purchasing domain layer (models/billing.py +
services/billing.py) already existed fully written but had zero HTTP
exposure. This adds the missing router, calling into the real service layer
(create_vendor_bill / execute_three_way_match / post_vendor_bill) rather than
reimplementing that logic inline.

Contract note vs. the currently-live app/plugins/purchases router: the live
plugin creates a PurchaseInvoice directly from supplier_id + item lines,
already CONFIRMED, and bumps Item.quantity_on_hand inline — no PO/GRN
matching. modules/purchasing's VendorBill is a stricter three-way-match
document: each VendorBillLine can *optionally* carry a po_line_id/grn_line_id
(both are nullable), and services/billing.post_vendor_bill() REQUIRES
match_state == MATCHED before it will post. execute_three_way_match() is the
only thing that sets MATCHED (0% tolerance: unmatched lines with no
po_line_id/grn_line_id default to zero variance and pass trivially, so bills
without PO/GRN links can still be matched-then-posted). Since posting always
requires a prior MATCHED state, this router exposes both actions:
  - POST /purchasing/bills/{id}/match  -> execute_three_way_match
  - POST /purchasing/bills/{id}/post   -> post_vendor_bill (the real
    state-transition function name in billing.py), which publishes the
    `purchase.bill_posted` DomainEvent inside the same transaction — verified
    against app/modules/accounting/consumers/purchasing_events.py's
    `process_bill_posted`, which subscribes to exactly that event name and
    reads payload["bill_id"]/["id"] plus subtotal/tax_total/total_amount, all
    of which post_vendor_bill's payload provides.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.database import get_tenant_db
from app.modules.purchasing.exceptions import (
    ThreeWayMatchError,
    VendorBillNotFoundError,
)
from app.modules.purchasing.models.billing import VendorBill, VendorBillStatus
from app.modules.purchasing.services.billing import (
    create_vendor_bill,
    execute_three_way_match,
    post_vendor_bill,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/purchasing/bills", tags=["Purchasing - Vendor Bills"])


class VendorBillLineIn(BaseModel):
    po_line_id: UUID | None = None
    grn_line_id: UUID | None = None
    qty_billed: Decimal
    unit_price: Decimal
    tax_code_id: UUID | None = None


class VendorBillCreateRequest(BaseModel):
    supplier_id: UUID
    bill_number: str
    lines: list[VendorBillLineIn]
    bill_date: date | None = None
    due_date: date | None = None
    currency: str = "EGP"
    fx_rate: Decimal = Decimal("1.000000")
    branch_id: UUID | None = None
    tax_total: Decimal = Decimal("0.0000")


@router.post(
    "",
    response_model=VendorBill,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT vendor bill",
)
async def create_bill(
    data: VendorBillCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> VendorBill:
    lines_data: list[dict[str, Any]] = [line.model_dump() for line in data.lines]
    try:
        bill = await create_vendor_bill(
            session=session,
            supplier_id=data.supplier_id,
            bill_number=data.bill_number,
            lines_data=lines_data,
            bill_date=data.bill_date,
            due_date=data.due_date,
            currency=data.currency,
            fx_rate=data.fx_rate,
            branch_id=data.branch_id,
            tax_total=data.tax_total,
        )
        await session.commit()
        return bill
    except (KeyError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "",
    response_model=list[VendorBill],
    summary="List vendor bills",
)
async def list_bills(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    status_filter: VendorBillStatus | None = Query(default=None, alias="status"),
    supplier_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[VendorBill]:
    q = select(VendorBill)
    if status_filter:
        q = q.where(VendorBill.status == status_filter)
    if supplier_id:
        q = q.where(VendorBill.supplier_id == supplier_id)
    q = q.order_by(VendorBill.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(q)
    return list(result.scalars().all())


@router.get(
    "/{bill_id}",
    response_model=VendorBill,
    summary="Get a vendor bill by ID (includes lines)",
)
async def get_bill(
    bill_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> VendorBill:
    result = await session.execute(
        select(VendorBill)
        .where(VendorBill.id == bill_id)
        .options(selectinload(VendorBill.lines))
    )
    bill = result.scalar_one_or_none()
    if not bill:
        raise HTTPException(status_code=404, detail=f"Vendor bill '{bill_id}' not found.")
    return bill


@router.post(
    "/{bill_id}/match",
    response_model=VendorBill,
    summary="Execute the strict (0% tolerance) three-way match against linked PO/GRN lines",
)
async def match_bill(
    bill_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> VendorBill:
    try:
        bill = await execute_three_way_match(session=session, bill_id=bill_id)
        await session.commit()
        return bill
    except VendorBillNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ThreeWayMatchError as exc:
        await session.commit()  # match_state=VARIANCE_BLOCKED + audit trail must persist
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/{bill_id}/post",
    response_model=VendorBill,
    summary="Post a MATCHED vendor bill to AP (publishes purchase.bill_posted)",
)
async def post_bill(
    bill_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> VendorBill:
    try:
        bill = await post_vendor_bill(session=session, bill_id=bill_id)
        await session.commit()
        return bill
    except VendorBillNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
