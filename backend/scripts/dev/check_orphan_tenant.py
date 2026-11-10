"""
check_orphan_tenant.py — P1 Item 6: after a registration attempt that the
browser showed as a "Network Error" / 503, check whether the public.tenants
/ public.users rows were left behind as an orphan (provisioning failed
mid-way and the rollback did NOT actually clean up) or whether the
transaction really did roll back cleanly (nothing found).

Searches by company-name prefix "P1 Item6" across all attempts.

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe check_orphan_tenant.py
"""
import asyncio


async def main() -> None:
    from sqlalchemy import select

    from app.core.db.database import public_session
    from app.modules.system.models import Tenant, User

    async with public_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name.ilike("P1 Item6%"))
        )
        tenants = result.scalars().all()
        print(f"Found {len(tenants)} tenant row(s) matching 'P1 Item6%':")
        for t in tenants:
            print(f"  id={t.id} name={t.name!r} schema_name={t.schema_name} "
                  f"status={t.status} provisioning_state={t.provisioning_state}")

            ures = await session.execute(select(User).where(User.tenant_id == t.id))
            users = ures.scalars().all()
            for u in users:
                print(f"    user: id={u.id} email={u.email} is_active={u.is_active}")

            # Check whether the tenant's schema actually exists in Postgres
            from sqlalchemy import text
            schema_check = await session.execute(text(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :s"
            ), {"s": t.schema_name})
            schema_exists = schema_check.scalar_one_or_none() is not None
            print(f"    schema '{t.schema_name}' actually exists in Postgres: {schema_exists}")

        if not tenants:
            print("  (none found — the failed attempt(s) rolled back cleanly, no orphan row)")


if __name__ == "__main__":
    asyncio.run(main())
