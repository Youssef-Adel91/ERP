"""
backend/scripts/dev/cleanup_test_tenants.py

Cleanup script for test tenants matching ui.test.trustcore*.
Drops their schemas and deletes public database rows.
Requires explicit confirmation unless --confirm is passed.
"""
import argparse
import asyncio
import sys

from sqlalchemy import delete, select, text
from app.core.db.database import AsyncSessionLocal, drop_tenant_schema
from app.modules.system.models import (
    Tenant,
    TenantMigration,
    TenantPlugin,
    TenantProvisioningJob,
    User,
)


async def cleanup(auto_confirm: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        # Find users matching ui.test.trustcore*
        user_stmt = select(User).where(User.email.like("ui.test.trustcore%"))
        res = await session.execute(user_stmt)
        users = res.scalars().all()

        if not users:
            print("No users matching 'ui.test.trustcore*' found.")
            return

        print(f"Found {len(users)} test user(s) matching 'ui.test.trustcore*':")
        tenant_ids = set()
        for u in users:
            print(f" - User: id={u.id}, email={u.email}, tenant_id={u.tenant_id}")
            if u.tenant_id:
                tenant_ids.add(u.tenant_id)

        # Fetch corresponding tenants
        tenants = []
        if tenant_ids:
            t_stmt = select(Tenant).where(Tenant.id.in_(tenant_ids))
            t_res = await session.execute(t_stmt)
            tenants = t_res.scalars().all()

        # Also find any tenants whose name or slug matches Test Co Six or ui-test-trustcore
        extra_t_stmt = select(Tenant).where(
            (Tenant.name.like("Test Co Six%"))
            | (Tenant.slug.like("ui-test-trustcore%"))
            | (Tenant.slug.like("test-co-six%"))
        )
        extra_t_res = await session.execute(extra_t_stmt)
        for t in extra_t_res.scalars().all():
            if t.id not in tenant_ids:
                tenants.append(t)
                tenant_ids.add(t.id)

        print(f"\nFound {len(tenants)} test tenant(s) to cleanup:")
        for t in tenants:
            print(f" - Tenant: id={t.id}, name={t.name!r}, slug={t.slug!r}, schema={t.schema_name!r}")

        # Safety verification: ensure none of the tenants/users look like production/non-test
        for u in users:
            if not u.email.startswith("ui.test.trustcore"):
                raise RuntimeError(f"ABORT: Safety check failed! Non-test user found: {u.email}")

        for t in tenants:
            # Check associated users
            u_check = (await session.execute(select(User).where(User.tenant_id == t.id))).scalars().all()
            for cu in u_check:
                if not cu.email.startswith("ui.test.trustcore"):
                    raise RuntimeError(
                        f"ABORT: Tenant {t.name} has non-test user: {cu.email}! Never touch non-test tenants."
                    )

        if not auto_confirm:
            ans = input("\nAre you sure you want to permanently delete these test tenants and schemas? (yes/no): ")
            if ans.strip().lower() != "yes":
                print("Aborted by user.")
                return

        print("\nProceeding with cleanup...")

        # 1. Drop schemas
        for t in tenants:
            schema = t.schema_name or f"tenant_{t.id}".replace("-", "_")
            print(f"Dropping schema {schema}...")
            await drop_tenant_schema(str(t.id))

        # 2. Delete public table references
        for tid in tenant_ids:
            await session.execute(delete(TenantPlugin).where(TenantPlugin.tenant_id == tid))
            await session.execute(delete(TenantMigration).where(TenantMigration.tenant_id == tid))
            await session.execute(delete(TenantProvisioningJob).where(TenantProvisioningJob.tenant_id == tid))
            # Delete WhatsApp config if present
            await session.execute(text("DELETE FROM public.whatsapp_tenant_configs WHERE tenant_id = :tid"), {"tid": tid})
            # Delete users
            await session.execute(delete(User).where(User.tenant_id == tid))
            # Delete tenant
            await session.execute(delete(Tenant).where(Tenant.id == tid))

        # Also delete any remaining users matching ui.test.trustcore%
        await session.execute(delete(User).where(User.email.like("ui.test.trustcore%")))

        await session.commit()
        print("Cleanup completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup ui.test.trustcore test tenants.")
    parser.add_argument("--confirm", action="store_true", help="Auto-confirm deletion.")
    args = parser.parse_args()
    asyncio.run(cleanup(auto_confirm=args.confirm))
