"""
app/modules/hr/api/payslips.py — Payslip API Endpoints
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db.database import get_tenant_db as get_db_session
from app.modules.hr.models.core import Payslip, PayslipStatus
from app.modules.hr.services.payroll import approve_payslip
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/hr/payslips", tags=["HR & Payroll"])


@router.get("", response_model=list[Payslip])
async def list_payslips(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    employee_id: str | None = Query(default=None),
    payslip_status: PayslipStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Lists payslips, optionally filtered by employee or status."""
    q = select(Payslip)
    if employee_id:
        q = q.where(Payslip.employee_id == employee_id)
    if payslip_status:
        q = q.where(Payslip.status == payslip_status)
    q = q.order_by(Payslip.period_start.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return result.scalars().all()


class PayslipCreate(BaseModel):
    employee_id: UUID
    period_start: date
    period_end: date
    basic_wage: Decimal = Decimal("0.0")
    allowances: Decimal = Decimal("0.0")
    deductions: Decimal = Decimal("0.0")

    @field_validator("basic_wage", "allowances", "deductions")
    @classmethod
    def _check_non_negative(cls, v: Decimal, info):
        if v < 0:
            raise ValueError(f"{info.field_name} cannot be negative.")
        return v


class PayslipAdjust(BaseModel):
    allowances: Decimal | None = None
    deductions: Decimal | None = None


@router.post("", response_model=Payslip)
async def generate_draft_payslip(
    data: PayslipCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """Generates a DRAFT payslip for an employee."""
    payslip = Payslip(**data.model_dump())
    payslip.status = PayslipStatus.DRAFT
    session.add(payslip)
    await session.commit()
    await session.refresh(payslip)
    return payslip


@router.patch("/{id}", response_model=Payslip)
async def adjust_payslip(
    id: UUID,
    data: PayslipAdjust,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """Adds allowances or deductions to a DRAFT payslip."""
    payslip = await session.get(Payslip, id)
    if not payslip:
        raise HTTPException(status_code=404, detail="Payslip not found")
    if payslip.status != PayslipStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only DRAFT payslips can be adjusted")

    if data.allowances is not None:
        if data.allowances < 0:
            raise HTTPException(status_code=422, detail="allowances cannot be negative.")
        payslip.allowances = data.allowances
    if data.deductions is not None:
        if data.deductions < 0:
            raise HTTPException(status_code=422, detail="deductions cannot be negative.")
        payslip.deductions = data.deductions

    session.add(payslip)
    await session.commit()
    await session.refresh(payslip)
    return payslip


@router.post("/{id}/approve")
async def approve(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Approves the payslip, computes net pay, and triggers the General Ledger
    posting atomically.
    """
    await approve_payslip(session, id)
    await session.commit()
    return {"message": "Payslip approved and GL Journal Entry posted successfully."}
