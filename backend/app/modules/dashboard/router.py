from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
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
    """Return aggregated financial metrics for the current tenant."""

    # Total Revenue (Credit on Revenue accounts ~4xxx)
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(TransactionLine.credit), Decimal("0")))
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code.like("4%"),
        ),
    )
    total_revenue = revenue_result.scalar_one() or Decimal("0")

    # Total Receivables (Debit on AR account 1200)
    ar_result = await db.execute(
        select(func.coalesce(func.sum(TransactionLine.debit), Decimal("0")))
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code == "1200",
        ),
    )
    total_receivables = ar_result.scalar_one() or Decimal("0")

    # Total Payables (Credit on AP account 2100)
    ap_result = await db.execute(
        select(func.coalesce(func.sum(TransactionLine.credit), Decimal("0")))
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code == "2100",
        ),
    )
    total_payables = ap_result.scalar_one() or Decimal("0")

    # Cash Balance (Debit minus Credit on Cash accounts ~11xx)
    cash_debit_result = await db.execute(
        select(func.coalesce(func.sum(TransactionLine.debit), Decimal("0")))
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code.like("11%"),
        ),
    )
    cash_credit_result = await db.execute(
        select(func.coalesce(func.sum(TransactionLine.credit), Decimal("0")))
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == JournalEntryStatus.POSTED,
            TransactionLine.account_code.like("11%"),
        ),
    )
    cash_balance = (cash_debit_result.scalar_one() or Decimal("0")) - (
        cash_credit_result.scalar_one() or Decimal("0")
    )

    return DashboardMetricsResponse(
        total_revenue=total_revenue,
        total_receivables=total_receivables,
        total_payables=total_payables,
        cash_balance=cash_balance,
    )
