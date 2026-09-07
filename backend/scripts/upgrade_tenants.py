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
    engine = create_async_engine(
        DATABASE_URL,
        future=True,
    )

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"))
        schemas = [row[0] for row in result.all()]

    await engine.dispose()

    print(f"Found {len(schemas)} tenant schemas.")

    # NOTE: previously this loop used check=True + sys.exit(1) on the first
    # failure, which meant one broken/unmigrated tenant schema silently
    # blocked every other (unrelated, independent) tenant schema from ever
    # being attempted in the same run — e.g. schemas that sort after a
    # failing one in `information_schema.schemata` order were never even
    # tried. Since each tenant schema is migrated independently (its own
    # alembic_version row, its own connection), one tenant's failure has no
    # bearing on whether another tenant's migration would succeed, so we now
    # continue past a failure, run every schema, and report a pass/fail
    # summary at the end. The process still exits non-zero if anything
    # failed, so CI/ops tooling calling this script still sees an error.
    succeeded: list[str] = []
    failed: list[tuple[str, int]] = []

    for schema in schemas:
        print(f"\n--- Upgrading schema: {schema} ---")
        # Run alembic upgrade head for this schema
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-n", "tenant", "-x", f"schema={schema}", "upgrade", "head"],
        )
        if result.returncode == 0:
            succeeded.append(schema)
        else:
            print(f"Error upgrading {schema}: alembic exited with code {result.returncode}")
            failed.append((schema, result.returncode))

    print("\n--- Tenant upgrade summary ---")
    print(f"Succeeded ({len(succeeded)}): {', '.join(succeeded) if succeeded else '(none)'}")
    if failed:
        print(f"Failed ({len(failed)}):")
        for schema, code in failed:
            print(f"  - {schema} (exit code {code})")
        sys.exit(1)
    else:
        print("\nAll tenant schemas upgraded successfully.")

if __name__ == "__main__":
    asyncio.run(main())
