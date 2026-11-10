"""
app/scripts/run_report_schedules.py — cron entry point for scheduled e-mailed reports

Usage (run daily, e.g. 07:00 Cairo time, from the backend directory):
    python -m app.scripts.run_report_schedules              # every active tenant
    python -m app.scripts.run_report_schedules <tenant_id>  # specific tenants

Each tenant is isolated: one broken tenant/schedule never stops the others.
Requires SMTP_HOST / SMTP_FROM_EMAIL in the environment, otherwise schedules
are left untouched (status "smtp_not_configured") and run once SMTP is set.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select

from app.core.db.database import AsyncSessionLocal, tenant_session
from app.modules.reporting.schedules import run_due_schedules
from app.modules.system.models import Tenant, TenantStatus

logger = logging.getLogger("report_schedules")


async def _active_tenant_ids() -> list[str]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        return [str(r[0]) for r in rows.all()]


async def run_for_tenant(tenant_id: str) -> list[dict]:
    async with tenant_session(tenant_id) as db:
        results = await run_due_schedules(db, tenant_id)
        await db.commit()
        return results


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    tenant_ids = sys.argv[1:] or await _active_tenant_ids()
    total = 0
    for tid in tenant_ids:
        try:
            ran = await run_for_tenant(tid)
            total += len(ran)
            for r in ran:
                logger.info("tenant=%s schedule=%s status=%s", tid, r["name"], r["status"])
        except Exception:
            logger.exception("tenant=%s: schedule run failed", tid)
    print(f"done: {total} schedule(s) processed across {len(tenant_ids)} tenant(s)")


if __name__ == "__main__":
    asyncio.run(main())
