"""
app/modules/finance/api/cheques.py — Cheques API Routes
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.modules.finance.models.cheques import Cheque, ChequeStatus, ChequeType
from app.modules.finance.services import cheque_service
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/api/v1/finance/cheques", tags=["cheques"])

# ── Schemas ──────────────────────────────────────────────────────────────────

class ChequeCreateRequest(BaseModel):
    cheque_number: str
    amount: Decimal
    issue_date: date
    due_date: date
    bank_name: str
    cheque_type: ChequeType
    contact_id: UUID
    invoice_id: Optional[UUID] = None
    transaction_id: Optional[UUID] = None


class ChequeResponse(BaseModel):
    id: UUID
    cheque_number: str
    amount: Decimal
    issue_date: date
    due_date: date
    bank_name: str
    cheque_type: ChequeType
    status: ChequeStatus
    contact_id: UUID
    invoice_id: Optional[UUID] = None
    transaction_id: Optional[UUID] = None
    created_at: datetime | None = None
    
    model_config = ConfigDict(from_attributes=True)


class ChequeListResponse(BaseModel):
    total: int
    items: List[ChequeResponse]

# ── Routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=ChequeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new cheque",
)
async def create_cheque(
    data: ChequeCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ChequeResponse:
    cheque = Cheque(
        cheque_number=data.cheque_number,
        amount=data.amount,
        issue_date=data.issue_date,
        due_date=data.due_date,
        bank_name=data.bank_name,
        cheque_type=data.cheque_type,
        contact_id=data.contact_id,
        invoice_id=data.invoice_id,
        transaction_id=data.transaction_id,
        created_by=current_user.id,
    )
    db.add(cheque)
    await db.commit()
    await db.refresh(cheque)
    return ChequeResponse.model_validate(cheque)


@router.get(
    "/",
    response_model=ChequeListResponse,
    summary="List cheques",
)
async def list_cheques(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    cheque_type: Optional[ChequeType] = Query(default=None),
    cheque_status: Optional[ChequeStatus] = Query(default=None, alias="status"),
    due_date_from: Optional[date] = Query(default=None),
    due_date_to: Optional[date] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ChequeListResponse:
    filters = []
    if cheque_type:
        filters.append(Cheque.cheque_type == cheque_type)
    if cheque_status:
        filters.append(Cheque.status == cheque_status)
    if due_date_from:
        filters.append(Cheque.due_date >= due_date_from)
    if due_date_to:
        filters.append(Cheque.due_date <= due_date_to)

    count_result = await db.execute(select(func.count()).select_from(Cheque).where(*filters))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Cheque).where(*filters).order_by(Cheque.due_date).limit(limit).offset(offset)
    )
    cheques = result.scalars().all()

    return ChequeListResponse(
        total=total,
        items=[ChequeResponse.model_validate(c) for c in cheques],
    )


@router.post(
    "/{cheque_id}/deposit",
    response_model=ChequeResponse,
    summary="Transition incoming cheque to deposited",
)
async def deposit_cheque_endpoint(
    cheque_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ChequeResponse:
    cheque = await cheque_service.deposit_cheque(db, cheque_id)
    return ChequeResponse.model_validate(cheque)


@router.post(
    "/{cheque_id}/clear",
    response_model=ChequeResponse,
    summary="Transition cheque to cleared",
)
async def clear_cheque_endpoint(
    cheque_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ChequeResponse:
    cheque = await cheque_service.clear_cheque(db, cheque_id)
    return ChequeResponse.model_validate(cheque)


@router.post(
    "/{cheque_id}/bounce",
    response_model=ChequeResponse,
    summary="Transition cheque to bounced",
)
async def bounce_cheque_endpoint(
    cheque_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ChequeResponse:
    cheque = await cheque_service.bounce_cheque(db, cheque_id)
    return ChequeResponse.model_validate(cheque)


@router.post(
    "/{cheque_id}/cancel",
    response_model=ChequeResponse,
    summary="Cancel a wrongly-entered cheque before it's deposited",
)
async def cancel_cheque_endpoint(
    cheque_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ChequeResponse:
    """
    The ChequeStatus enum already had a CANCELLED state but no endpoint
    ever set it — a cheque entered with a typo'd number/amount had no way
    to be voided short of leaving it PENDING forever. Only allowed from
    PENDING: once a cheque has been deposited/cleared/bounced it's a real
    bank event that already happened and must be corrected through the
    proper reversal flow, not silently erased.
    """
    cheque = await db.get(Cheque, cheque_id)
    if not cheque:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cheque not found.")
    if cheque.status != ChequeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only a PENDING cheque can be cancelled (current status: {cheque.status.value}).",
        )
    cheque.status = ChequeStatus.CANCELLED
    db.add(cheque)
    await db.commit()
    await db.refresh(cheque)
    return ChequeResponse.model_validate(cheque)
