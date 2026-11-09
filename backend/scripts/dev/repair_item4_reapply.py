"""
repair_item4_reapply.py — re-run the FIXED i5d6e7f8g9h0 migration.

Why this script exists (not just `python upgrade_tenants.py` again):
Alembic tracks applied migrations by revision ID in each schema's
`alembic_version` table, not by file content. All 14 tenants already have
`i5d6e7f8g9h0` recorded as applied (from the buggy version), so a plain
`alembic upgrade head` is a no-op even after the migration file on disk was
fixed -- it thinks it already ran.

This script forces the corrected upgrade() to actually execute again, for
every tenant schema, by:
  1. `alembic -x schema=<schema> downgrade h4c5d6e7f8g9`  (moves the
     version pointer back one step -- downgrade() is an intentional no-op,
     it does NOT touch any data, see the migration file's downgrade()
     docstring)
  2. `alembic -x schema=<schema> upgrade head`             (re-runs the
     NOW-FIXED upgrade() function, which is self-healing: it will insert
     only the genuinely missing month(s) and leave everything else alone)

Safe to run on tenants that were NOT affected by the bug too -- the fixed
upgrade() is idempotent, so it will insert 0 rows for them.

Usage (from backend/, same venv as upgrade_tenants.py):
    python repair_item4_reapply.py
"""
import asyncio
import os
import sys
import subprocess

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

    await engine.dispose()

    print(f"Found {len(schemas)} tenant schemas.")
    for schema in schemas:
        print(f"\n--- Repairing schema: {schema} ---")
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "-n", "tenant", "-x", f"schema={schema}", "downgrade", "h4c5d6e7f8g9"],
                check=True,
            )
            subprocess.run(
                [sys.executable, "-m", "alembic", "-n", "tenant", "-x", f"schema={schema}", "upgrade", "head"],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error repairing {schema}: {e}")
            sys.exit(1)

    print("\nAll tenant schemas re-applied against the fixed migration.")


if __name__ == "__main__":
    asyncio.run(main())
