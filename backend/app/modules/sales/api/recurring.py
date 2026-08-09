"""
app/modules/sales/api/recurring.py — Recurring Invoice Worker Trigger API

app/modules/sales/services/recurring_worker.py's generate_due_recurring_invoices
is a background-job-style function (scans ALL due RecurringInvoiceProfiles for
the tenant and generates SalesInvoices for each) rather than a per-resource
REST action, so it is exposed as a single admin-triggerable POST endpoint
rather than forced into an odd per-profile REST shape. Intended to be called
by a scheduler/cron client hitting this endpoint per tenant, or manually by
an admin.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.sales.services.recurring_worker import generate_due_recurring_invoices
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/recurring-invoices", tags=["Sales - Recurring Invoices"])


class RunRecurringInvoicesResponse(BaseModel):
    status: str = "ok"


@router.post(
    "/run",
    response_model=RunRecurringInvoicesResponse,
    summary="Admin-triggered run: generate SalesInvoices for all due recurring invoice profiles",
)
async def run_recurring_invoices(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> RunRecurringInvoicesResponse:
    await generate_due_recurring_invoices(session)
    await session.commit()
    return RunRecurringInvoicesResponse()
