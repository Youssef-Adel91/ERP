"""
verify_item4_periods.py — P1 Item 4 live idempotency proof.

Run this BEFORE the 1st `python upgrade_tenants.py`, AFTER the 1st run, and
AFTER the 2nd run. Paste all three outputs back verbatim.

For every tenant schema it prints:
  - total accounting_periods row count
  - how many of those rows are "wide" (duration > 5000 days) -- should be
    1 before migration, 0 after
  - how many are real monthly periods (duration <= 31 days)
  - min(start_date) / max(end_date) across all periods (should stay
    2020-01-01 .. 2099-12-31 before AND after -- same total coverage, just
    sliced into months)
  - how many periods have is_closed = true (should be 0 right after
    migration -- "every period created OPEN by default")

Usage (from the backend/ directory, same venv as upgrade_tenants.py):
    python verify_item4_periods.py
"""
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.environ["DATABASE_URL"]


async def main():
    engine = create_async_engine(DATABASE_URL, future=True)

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%' ORDER BY schema_name")
        )
        schemas = [row[0] for row in result.all()]

    print(f"Found {len(schemas)} tenant schemas.\n")

    async with engine.connect() as conn:
        for schema in schemas:
            has_table = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_name = 'accounting_periods'"
                ),
                {"schema": schema},
            )
            if not has_table.scalar():
                print(f"--- {schema}: no accounting_periods table, skipping ---\n")
                continue

            total = (
                await conn.execute(text(f'SELECT count(*) FROM "{schema}".accounting_periods'))
            ).scalar()
            wide = (
                await conn.execute(
                    text(
                        f'SELECT count(*) FROM "{schema}".accounting_periods '
                        "WHERE (end_date - start_date) > make_interval(days => 5000)"
                    )
                )
            ).scalar()
            monthly = (
                await conn.execute(
                    text(
                        f'SELECT count(*) FROM "{schema}".accounting_periods '
                        "WHERE (end_date - start_date) <= make_interval(days => 31)"
                    )
                )
            ).scalar()
            bounds = (
                await conn.execute(
                    text(f'SELECT min(start_date), max(end_date) FROM "{schema}".accounting_periods')
                )
            ).first()
            closed = (
                await conn.execute(
                    text(f'SELECT count(*) FROM "{schema}".accounting_periods WHERE is_closed = true')
                )
            ).scalar()

            print(f"--- {schema} ---")
            print(f"  total periods       : {total}")
            print(f"  wide (>5000d) periods: {wide}")
            print(f"  monthly (<=31d) periods: {monthly}")
            print(f"  coverage             : {bounds[0]} .. {bounds[1]}")
            print(f"  closed periods        : {closed}")
            print()

    await engine.dispose()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
