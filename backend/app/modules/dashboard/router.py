from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.accounting.models import JournalEntry, JournalEntryStatus, TransactionLine
from app.modules.contacts.models import Contact
from app.modules.sales.models.core import SalesOrder
from app.modules.system.dependencies import CurrentUser

router = APIRouter()


class DashboardMetricsResponse(BaseModel):
    total_revenue: Decimal
    total_receivables: Decimal
    total_payables: Decimal
    cash_balance: Decimal
    # Order count / new customers this calendar month, plus their
    # percentage change vs the previous calendar month — replaces the
    # frontend's previously hardcoded "1,842" / "312" KPI cards and their
    # hardcoded "8%+"/"2%-" trend badges (see docs/Nexus_ERP_Audit_Report.md
    # §15, line 580: mock dashboard data flagged as a High-priority issue).
    # trend_pct is None when there's no prior-month baseline to compare
    # against (previous month had zero — a percentage change is undefined,
    # not zero, in that case).
    order_count: int
    order_count_trend_pct: float | None
    new_customers_count: int
    new_customers_trend_pct: float | None


def _month_bounds(now: datetime) -> tuple[datetime, datetime, datetime]:
    """Returns (start_of_this_month, start_of_prev_month, start_of_next_month)."""
    start_of_this_month = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 1:
        start_of_prev_month = datetime(now.year - 1, 12, 1, tzinfo=UTC)
    else:
        start_of_prev_month = datetime(now.year, now.month - 1, 1, tzinfo=UTC)
    if now.month == 12:
        start_of_next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        start_of_next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return start_of_this_month, start_of_prev_month, start_of_next_month


def _trend_pct(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


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
    """Return aggregated financial + operational metrics for the current tenant."""

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

    # ── Order count + new customers, this month vs previous month ──────────
    now = datetime.now(UTC)
    start_this_month, start_prev_month, start_next_month = _month_bounds(now)

    order_count_this = (await db.execute(
        select(func.count(SalesOrder.id)).where(SalesOrder.created_at >= start_this_month)
    )).scalar_one()
    order_count_prev = (await db.execute(
        select(func.count(SalesOrder.id)).where(
            SalesOrder.created_at >= start_prev_month,
            SalesOrder.created_at < start_this_month,
        )
    )).scalar_one()

    new_customers_this = (await db.execute(
        select(func.count(Contact.id)).where(Contact.created_at >= start_this_month)
    )).scalar_one()
    new_customers_prev = (await db.execute(
        select(func.count(Contact.id)).where(
            Contact.created_at >= start_prev_month,
            Contact.created_at < start_this_month,
        )
    )).scalar_one()

    return DashboardMetricsResponse(
        total_revenue=total_revenue,
        total_receivables=total_receivables,
        total_payables=total_payables,
        cash_balance=cash_balance,
        order_count=order_count_this,
        order_count_trend_pct=_trend_pct(order_count_this, order_count_prev),
        new_customers_count=new_customers_this,
        new_customers_trend_pct=_trend_pct(new_customers_this, new_customers_prev),
    )


@router.get(
    "/export.xlsx",
    summary="Export dashboard summary + recent transactions as an Excel workbook",
    tags=["Dashboard"],
)
async def export_dashboard_excel(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> Response:
    """
    Replaces the frontend's previous hand-rolled 4-number CSV export (see
    docs/Nexus_ERP_Audit_Report.md §15, line 588: "the only export
    anywhere in the whole system is a trivial CSV of 4 dashboard numbers")
    with a real .xlsx workbook: a summary sheet (the same metrics
    GET /dashboard/metrics returns) plus a sheet of recent posted journal
    entries. Uses openpyxl, already a project dependency (added for
    app.plugins.recruitment's Excel *import* — this is this codebase's
    first Excel *export*, so this function isn't replicating an existing
    pattern; it establishes one for the export/report gap the audit flagged).
    """
    try:
        import openpyxl
        from openpyxl.styles import Font
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl is required for Excel export. Run: pip install openpyxl",
        )

    metrics = await get_dashboard_metrics(current_user, db)

    entries_result = await db.execute(
        select(JournalEntry)
        .where(JournalEntry.status == JournalEntryStatus.POSTED)
        .order_by(JournalEntry.created_at.desc())
        .limit(50)
    )
    entries = entries_result.scalars().unique().all()

    wb = openpyxl.Workbook()

    summary_ws = wb.active
    summary_ws.title = "Summary"
    summary_ws.append(["Metric", "Value"])
    for cell in summary_ws[1]:
        cell.font = Font(bold=True)
    summary_ws.append(["Total Revenue (EGP)", float(metrics.total_revenue)])
    summary_ws.append(["Total Receivables (EGP)", float(metrics.total_receivables)])
    summary_ws.append(["Total Payables (EGP)", float(metrics.total_payables)])
    summary_ws.append(["Cash Balance (EGP)", float(metrics.cash_balance)])
    summary_ws.append(["Orders This Month", metrics.order_count])
    summary_ws.append(["New Customers This Month", metrics.new_customers_count])
    for col in ("A", "B"):
        summary_ws.column_dimensions[col].width = 28

    txn_ws = wb.create_sheet("Recent Transactions")
    txn_ws.append(["Reference", "Description", "Date", "Status", "Total Debit (EGP)"])
    for cell in txn_ws[1]:
        cell.font = Font(bold=True)
    for entry in entries:
        total_debit = sum(float(line.debit or 0) for line in entry.lines)
        txn_ws.append([
            entry.reference or "",
            entry.description,
            entry.created_at.strftime("%Y-%m-%d") if entry.created_at else "",
            entry.status.value if hasattr(entry.status, "value") else str(entry.status),
            total_debit,
        ])
    for col, width in zip("ABCDE", (18, 40, 14, 12, 18)):
        txn_ws.column_dimensions[col].width = width

    buf = io.BytesIO()
    wb.save(buf)
    filename = f"dashboard-export-{datetime.now(UTC).strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
