"""Create any tables missing from EVERY existing tenant schema (idempotent).

Use after adding a model to `tenant_tables` in app/core/db/database.py, so
tenants provisioned earlier pick up the new tables. Safe to re-run
(create_all checkfirst). Does NOT reseed the chart of accounts.

    python -m scripts.dev.sync_tenant_tables
"""
import asyncio

from sqlalchemy import select

from app.core.db.database import _provision_tenant_schema_internal, public_session
from app.modules.system.models import Tenant


async def main() -> None:
    async with public_session() as s:
        ids = [str(t.id) for t in (await s.execute(select(Tenant))).scalars().all()]
    for tid in ids:
        await _provision_tenant_schema_internal(tid, seed_coa=False)
        print("synced", tid)


if __name__ == "__main__":
    asyncio.run(main())
