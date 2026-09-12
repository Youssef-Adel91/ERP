"""
app/modules/reporting/router.py — Reporting REST API (Phase B: Expanded Dashboards)

A plain, authenticated REST surface over app.modules.reporting.service's
typed report functions — the SAME functions REPORT_REGISTRY hands to the
AI Bot for function-calling (see that module's docstring). Nothing here
is a new query or a new number: every endpoint is a thin wrapper so the
frontend dashboard can render a real chart/widget without going through
the AI Bot's natural-language layer, while guaranteeing the dashboard and
the AI Bot can never disagree about a number — they're the same function
call.

Read-only by construction, same guardrail as app.modules.ai and
app.modules.reporting.service.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.reporting.service import (
    get_customer_trust_profile,
    get_expense_breakdown,
    get_overdue_invoices,
    get_revenue_trend,
    get_revenue_variance_analysis,
    get_top_customers_by_revenue,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/reporting", tags=["Reporting"])


@router.get("/revenue-trend", summary="Monthly revenue for the last N months")
async def revenue_trend(
    current_user: CurrentUser,
    months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    return await get_revenue_trend(db, months=months)


@router.get("/expense-breakdown", summary="Expense totals this month, grouped by account")
async def expense_breakdown(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    return await get_expense_breakdown(db)


@router.get("/revenue-variance", summary="Why revenue changed this month vs last")
async def revenue_variance(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    return await get_revenue_variance_analysis(db)


@router.get("/top-customers", summary="Top customers by posted/paid invoice revenue")
async def top_customers(
    current_user: CurrentUser,
    limit: int = Query(default=5, ge=1, le=50),
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    return await get_top_customers_by_revenue(db, limit=limit)


@router.get("/overdue-invoices", summary="Overdue posted invoices, oldest first")
async def overdue_invoices(
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    return await get_overdue_invoices(db, limit=limit)


@router.get(
    "/customer-trust",
    summary="Cross-tenant Trust Network risk band for a customer, looked up by name (Phase F)",
)
async def customer_trust(
    current_user: CurrentUser,
    customer_name: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_tenant_db),
) -> dict:
    """
    Resolves customer_name to this tenant's own Contact record, then
    queries the real cross-tenant Trust Network for that contact's phone
    number — the SAME engine and the SAME gates (reciprocity, K-anonymity)
    as the manual phone-lookup form on /dashboard/trust. Needs tenant_id
    explicitly (see get_customer_trust_profile's docstring) since the
    Trust Network lives in the shared public schema.
    """
    return await get_customer_trust_profile(db, tenant_id=str(current_user.tenant_id), customer_name=customer_name)
