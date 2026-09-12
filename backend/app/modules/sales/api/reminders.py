"""
app/modules/sales/api/reminders.py — Overdue Invoice Reminder Trigger API

app/modules/sales/services/reminders.py's process_overdue_reminders is a
background-job-style batch scan (finds all POSTED-and-overdue SalesInvoices
for the tenant and publishes an InvoiceOverdueEvent per invoice) rather than
a per-resource REST action, so — same reasoning as recurring.py — it is
exposed as a single admin-triggerable POST endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.sales.services.reminders import process_overdue_reminders
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/reminders", tags=["Sales - Reminders"])


class RunRemindersResponse(BaseModel):
    status: str = "ok"


@router.post(
    "/run",
    response_model=RunRemindersResponse,
    summary="Admin-triggered run: publish InvoiceOverdueEvent for every overdue posted invoice",
)
async def run_overdue_reminders(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> RunRemindersResponse:
    await process_overdue_reminders(session, tenant_id=current_user.tenant_id)
    await session.commit()
    return RunRemindersResponse()
