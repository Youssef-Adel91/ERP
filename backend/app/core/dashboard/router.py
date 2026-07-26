from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.modules.accounting.models import JournalEntry, JournalEntryStatus, TransactionLine
from app.modules.system.dependencies import CurrentUser

router = APIRouter()

class DashboardMetricsResponse(BaseModel):
    total_revenue: Decimal
    total_receivables: Decimal
    total_payables: Decimal
    cash_balance: Decimal

@router.get(
    "/metrics",
    response_model=DashboardMetricsResponse,
    summary="Get real-time dashboard metrics",
    tags=["Dashboard"],
)
async def get_dashboard_metrics(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> DashboardMetricsResponse:
    # We only sum lines for POSTED entries
    stmt = (
        select(
            TransactionLine.account_code,
            func.sum(TransactionLine.debit).label("total_debit"),
            func.sum(TransactionLine.credit).label("total_credit"),
        )
        .join(JournalEntry)
        .where(JournalEntry.status == JournalEntryStatus.POSTED)
        .where(TransactionLine.account_code.in_(["4010", "1200", "2100", "1100"]))
        .group_by(TransactionLine.account_code)
    )
    
    result = await db.execute(stmt)
    rows = result.all()

    # Initialize variables
    total_revenue = Decimal("0")
    total_receivables = Decimal("0")
    total_payables = Decimal("0")
    cash_balance = Decimal("0")

    for row in rows:
        code = row.account_code
        debit = row.total_debit or Decimal("0")
        credit = row.total_credit or Decimal("0")
        
        if code == "4010": # Revenue (Credit normal)
            total_revenue = credit - debit
        elif code == "1200": # AR (Debit normal)
            total_receivables = debit - credit
        elif code == "2100": # AP (Credit normal)
            total_payables = credit - debit
        elif code == "1100": # Cash (Debit normal)
            cash_balance = debit - credit

    return DashboardMetricsResponse(
        total_revenue=total_revenue,
        total_receivables=total_receivables,
        total_payables=total_payables,
        cash_balance=cash_balance,
    )
