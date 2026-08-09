"""
app/modules/imports/api/dossiers.py — Import Cycle API Endpoints
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, field_validator
from decimal import Decimal

from app.core.db.database import get_tenant_db as get_db_session

from app.modules.imports.models.core import ImportDossier, ImportExpense, ImportStatus
from app.modules.imports.services.landed_cost import apply_landed_costs
from app.modules.system.dependencies import CurrentUser


router = APIRouter(prefix="/imports/dossiers", tags=["Imports"])

class DossierCreate(BaseModel):
    dossier_number: str
    supplier_id: UUID
    currency: str = "EGP"
    fx_rate: Decimal = Decimal("1.0")

class ExpenseCreate(BaseModel):
    expense_type: str
    amount: Decimal
    vendor_id: UUID | None = None

    @field_validator("amount")
    @classmethod
    def _amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than zero.")
        return v


@router.post("", response_model=ImportDossier)
async def create_dossier(
    data: DossierCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """Creates a new Import Dossier wrapper."""
    dossier = ImportDossier(
        dossier_number=data.dossier_number,
        supplier_id=data.supplier_id,
        currency=data.currency,
        fx_rate=data.fx_rate,
        status=ImportStatus.OPEN,
        created_by=current_user.id,
    )
    session.add(dossier)
    await session.commit()
    await session.refresh(dossier)
    return dossier


@router.get("", response_model=list[ImportDossier])
async def list_dossiers(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    dossier_status: ImportStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Lists all import dossiers, optionally filtered by status."""
    q = select(ImportDossier)
    if dossier_status:
        q = q.where(ImportDossier.status == dossier_status)
    q = q.order_by(ImportDossier.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/{id}", response_model=ImportDossier)
async def get_dossier(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """Fetches a dossier by ID."""
    dossier = await session.get(ImportDossier, id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier not found")
    return dossier


@router.get("/{id}/expenses", response_model=list[ImportExpense])
async def list_dossier_expenses(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """Lists all expenses logged against a dossier."""
    result = await session.execute(
        select(ImportExpense).where(ImportExpense.dossier_id == id).order_by(ImportExpense.created_at),
    )
    return result.scalars().all()


@router.post("/{id}/expenses", response_model=ImportExpense)
async def add_expense(
    id: UUID,
    data: ExpenseCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """Logs an expense against the specified dossier."""
    dossier = await session.get(ImportDossier, id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier not found")
    if dossier.status != ImportStatus.OPEN:
        # Expenses feed the landed-cost distribution that runs at close —
        # adding one afterward would silently never be allocated to any
        # cost layer.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot add an expense to a dossier that is already closed.",
        )

    expense = ImportExpense(
        dossier_id=id,
        expense_type=data.expense_type,
        amount=data.amount,
        vendor_id=data.vendor_id,
        created_by=current_user.id,
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    return expense


@router.delete("/{id}/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    id: UUID,
    expense_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Removes a wrongly-logged expense. Only while the dossier is still OPEN
    — once closed, landed costs have already been distributed across
    inventory cost layers using this expense, so deleting it after the
    fact would desync the books from the physical cost allocation.
    """
    dossier = await session.get(ImportDossier, id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier not found")
    if dossier.status != ImportStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove an expense from a dossier that is already closed.",
        )

    expense = await session.get(ImportExpense, expense_id)
    if not expense or expense.dossier_id != id:
        raise HTTPException(status_code=404, detail="Expense not found on this dossier.")

    await session.delete(expense)
    await session.commit()


@router.post("/{id}/close")
async def close_dossier(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Closes the dossier and triggers the mathematical distribution of landed costs
    across the associated inventory cost layers under a strict transaction.
    """
    await apply_landed_costs(session, id)
    await session.commit()
    return {"message": "Dossier closed and landed costs successfully applied"}
