"""
scripts/repair_tenant_migrations.py — Bring every existing tenant schema up
to the current Alembic head.

WHY THIS EXISTS:
Any tenant registered BEFORE the tenant-migration-chain duplicate-table bug
was fixed (see alembic/tenant/versions/f93809b48226_...) may have had its
schema provisioning fail partway through, or been stamped at an old
revision. That tenant's schema is then permanently missing every table
created by later migrations (eta_tenant_configs, eta_documents, egs_codes,
purchasing bills, cheques, etc.) -- any endpoint touching those tables
returns a 500 ("relation does not exist") forever, even though brand-new
tenants provisioned today work fine.

Alembic's `upgrade head` is idempotent per-schema: it only applies
revisions after whatever that schema's own alembic_version row currently
points to, so running this against an already-up-to-date tenant is a safe
no-op.

USAGE:
    cd backend
    python scripts/repair_tenant_migrations.py                 # repair ALL tenants
    python scripts/repair_tenant_migrations.py --email you@x.com  # repair one tenant by user email
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _normalize_database_url(raw: str) -> str:
    url = raw.strip()
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    elif url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    url = url.replace("sslmode=require", "ssl=require")
    url = url.replace("sslmode=verify-full", "ssl=require")
    # asyncpg doesn't understand channel_binding at all -- drop it.
    import re
    url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
    return url


async def main() -> None:
    email = None
    if "--email" in sys.argv:
        email = sys.argv[sys.argv.index("--email") + 1]

    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        from app.core.config import Settings
        raw_url = Settings().DATABASE_URL
    os.environ["DATABASE_URL"] = _normalize_database_url(raw_url)

    from sqlalchemy import select
    from app.core.db.database import engine
    from app.core.tenancy.migrations import TenantMigrationOrchestrator
    from app.modules.system.models import Tenant, User
    from sqlalchemy.ext.asyncio import AsyncSession

    orchestrator = TenantMigrationOrchestrator()

    async with AsyncSession(engine) as session:
        if email:
            result = await session.execute(
                select(Tenant).join(User, User.tenant_id == Tenant.id).where(User.email == email)
            )
        else:
            result = await session.execute(select(Tenant))
        tenants = result.scalars().all()

    if not tenants:
        print(f"No tenant found{f' for email={email}' if email else ''}.")
        return

    print(f"Repairing {len(tenants)} tenant schema(s)...\n")
    for tenant in tenants:
        print(f"--- {tenant.name} ({tenant.schema_name}) ---")
        try:
            await orchestrator._migrate_tenant(tenant.schema_name)
            print("OK\n")
        except Exception as exc:
            print(f"FAILED: {exc}\n")

    print("Done. Re-test the affected pages now.")


if __name__ == "__main__":
    asyncio.run(main())
