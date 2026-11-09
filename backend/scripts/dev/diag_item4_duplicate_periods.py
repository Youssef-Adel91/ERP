"""
diag_item4_duplicate_periods.py — diagnose why a CLOSED 2024-06 period did
not block a posting dated 2024-06-15.

Lists EVERY accounting_periods row in tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f
whose [start_date, end_date] range covers 2024-06-15, and separately every
row named exactly "2024-06". If there is more than one row in either list,
post_journal_entry()'s `.scalars().first()` may be picking a different
(OPEN) row than the one closed via the UI (id 3369ee21-c53c-4597-8993-277c0a89618f).

Usage (from backend/, same venv as the other scripts):
    python diag_item4_duplicate_periods.py
"""
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.environ["DATABASE_URL"]
SCHEMA = "tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f"


async def main():
    engine = create_async_engine(DATABASE_URL, future=True)
    async with engine.connect() as conn:
        print("=" * 70)
        print("Rows whose range covers 2024-06-15:")
        print("=" * 70)
        rows = (
            await conn.execute(
                text(
                    f'SELECT id, name, start_date, end_date, is_closed, closed_by, closed_at '
                    f'FROM "{SCHEMA}".accounting_periods '
                    f"WHERE start_date <= '2024-06-15 23:59:59' AND end_date >= '2024-06-15 00:00:00' "
                    f"ORDER BY start_date"
                )
            )
        ).fetchall()
        for r in rows:
            print(f"  id={r[0]} name={r[1]!r} start={r[2]} end={r[3]} is_closed={r[4]} closed_by={r[5]} closed_at={r[6]}")
        print(f"  -> {len(rows)} row(s) match this date range")

        print()
        print("=" * 70)
        print('Rows literally named "2024-06":')
        print("=" * 70)
        rows2 = (
            await conn.execute(
                text(
                    f'SELECT id, name, start_date, end_date, is_closed, closed_by, closed_at '
                    f'FROM "{SCHEMA}".accounting_periods '
                    f"WHERE name = '2024-06' ORDER BY start_date"
                )
            )
        ).fetchall()
        for r in rows2:
            print(f"  id={r[0]} name={r[1]!r} start={r[2]} end={r[3]} is_closed={r[4]} closed_by={r[5]} closed_at={r[6]}")
        print(f"  -> {len(rows2)} row(s) named '2024-06'")

        print()
        print("=" * 70)
        print("Total row count and duplicate-name check across ALL periods:")
        print("=" * 70)
        total = (await conn.execute(text(f'SELECT count(*) FROM "{SCHEMA}".accounting_periods'))).scalar()
        dups = (
            await conn.execute(
                text(
                    f'SELECT name, count(*) c FROM "{SCHEMA}".accounting_periods '
                    f"GROUP BY name HAVING count(*) > 1 ORDER BY name"
                )
            )
        ).fetchall()
        print(f"  total periods: {total}")
        print(f"  duplicate names: {dups if dups else 'none'}")

    await engine.dispose()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
