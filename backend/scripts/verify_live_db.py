"""
scripts/verify_live_db.py — One-shot live-Postgres verification.

WHY THIS EXISTS:
Every fix in this codebase (Alembic tenant migrations, tenant provisioning,
double-booking locks, folio math, GL posting) has only ever been verified
against SQLite in-memory or by static analysis (ast.parse / import checks)
-- there has never been a real Postgres database available to actually run
against. This script is the first real end-to-end check.

WHAT IT DOES, in order, against whatever DATABASE_URL you give it:
  1. Runs the PUBLIC schema Alembic migrations (alembic -n public upgrade head).
  2. Creates one throwaway tenant row directly (bypassing the register
     endpoint's HTTP/JWT layer, but exercising the exact same provisioning
     function it calls).
  3. Provisions that tenant's schema via the REAL code path fixed this
     session: CREATE SCHEMA + `alembic -n tenant -x schema=<x> upgrade head`
     (NOT create_all -- see app/core/db/database.py's
     _provision_tenant_schema_internal docstring). This is the part that
     could never be verified before: does the tenant Alembic chain
     actually apply cleanly against a real database?
  4. Verifies: the new schema has tables, alembic_version is stamped, and
     the default Chart of Accounts got seeded.
  5. Prints a clear PASS/FAIL report and CLEANS UP after itself (drops the
     test tenant schema and public rows) unless --keep is passed.

USAGE:
    cd backend
    pip install -r requirements.txt   # if not already installed
    export DATABASE_URL="postgresql+asyncpg://neondb_owner:npg_AzPj0lZiwOf7@ep-polished-art-ayxyzvkg.c-5.us-east-2.aws.neon.tech/neondb?ssl=require"
    python scripts/verify_live_db.py

    # to leave the test tenant in place for manual inspection afterward:
    python scripts/verify_live_db.py --keep

NOTE ON THE CONNECTION STRING:
Neon gives you a `postgresql://...?sslmode=require` URL. Two changes are
required for this app:
  - driver prefix: `postgresql://` -> `postgresql+asyncpg://` (this app
    uses the async asyncpg driver throughout, not psycopg2/psycopg3)
  - ssl param name: `sslmode=require` (libpq-style) -> `ssl=require`
    (asyncpg-style) -- asyncpg does not understand `sslmode`.
This script does that substitution for you automatically if you pass the
raw Neon-style URL, so you don't have to edit it by hand.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
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
    return url


def _run(label: str, *cmd: str, env: dict) -> None:
    print(f"\n--- {label} ---")
    print("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(BACKEND_ROOT), env=env, capture_output=True, text=True)
    print(result.stdout[-4000:])
    if result.returncode != 0:
        print(result.stderr[-4000:])
        raise SystemExit(f"FAILED: {label} (exit {result.returncode})")


async def main() -> None:
    keep = "--keep" in sys.argv

    # DATABASE_URL is normally only read from backend/.env by pydantic-settings
    # INSIDE the app process — it's never exported to the shell itself, so
    # os.environ won't have it unless the caller explicitly set it.
    #
    # Resolve it the exact same way the app itself does — by importing
    # app.core.config.settings (which loads backend/.env via pydantic-settings)
    # — rather than re-parsing .env ourselves with a second library. A first
    # attempt at this using `dotenv_values()` directly silently returned
    # nothing on Windows with this repo's non-ASCII (Arabic) parent directory
    # path; importing the app's own already-working settings loader sidesteps
    # that entirely instead of chasing the encoding bug.
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        try:
            from app.core.config import Settings
            raw_url = Settings().DATABASE_URL
        except Exception as exc:
            print(f"(Could not load DATABASE_URL via app.core.config.Settings: {exc})")

    if not raw_url or raw_url.startswith("postgresql+asyncpg://postgres:postgres@localhost"):
        raise SystemExit(
            "DATABASE_URL not found (or still the localhost default) in the "
            "environment or in backend/.env.\n"
            "Either add DATABASE_URL=... to backend/.env, or set it directly:\n"
            '  $env:DATABASE_URL="postgresql+asyncpg://user:pass@host/db?ssl=require"   (PowerShell)\n'
            '  export DATABASE_URL="postgresql+asyncpg://user:pass@host/db?ssl=require" (bash)'
        )

    database_url = _normalize_database_url(raw_url)
    os.environ["DATABASE_URL"] = database_url

    env = os.environ.copy()

    # -- Step 1: public schema migrations --
    _run("Public schema migrations", sys.executable, "-m", "alembic", "-n", "public", "upgrade", "head", env=env)

    # -- Step 2 & 3: create + provision a throwaway tenant --
    from sqlalchemy import text
    from app.core.db.database import engine, tenant_session
    from app.core.db.database import _provision_tenant_schema_internal

    test_tenant_id = uuid.uuid4()
    schema = f"tenant_{str(test_tenant_id).replace('-', '_')}"
    slug = f"live-db-verify-{str(test_tenant_id)[:8]}"

    print(f"\n--- Creating throwaway tenant row (id={test_tenant_id}) ---")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO public.tenants "
                "(id, name, slug, schema_name, provisioning_state, plan, "
                " trust_consent, country_code, currency_code, timezone, status, active_plugins) "
                "VALUES "
                "(:id, :name, :slug, :schema_name, "
                " CAST('CREATED' AS provisioningstate), "
                " CAST('FREE' AS plantier), "
                " false, 'EG', 'EGP', 'Africa/Cairo', "
                " CAST('PENDING_SETUP' AS tenantstatus), "
                " '[]')"
            ),
            {
                "id": test_tenant_id,
                "name": "Live DB Verify Tenant",
                "slug": slug,
                "schema_name": schema,
            },
        )
    print("OK")

    print("\n--- Provisioning tenant schema via REAL alembic tenant chain ---")
    print("(this is the exact code path fixed to stop using create_all())")
    await _provision_tenant_schema_internal(str(test_tenant_id), seed_coa=True)
    print("OK -- no exception raised.")

    # -- Step 4: verify --
    print("\n--- Verifying provisioned schema ---")
    checks_passed = True

    async with engine.begin() as conn:
        table_count = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = :schema"
                ),
                {"schema": schema},
            )
        ).scalar_one()
        print(f"Tables in {schema}: {table_count}")
        if table_count < 10:
            print("FAIL: expected dozens of tenant tables, found suspiciously few.")
            checks_passed = False

        version_row = (
            await conn.execute(
                text(f'SELECT version_num FROM "{schema}".alembic_version')
            )
        ).scalar_one_or_none()
        print(f"alembic_version in {schema}: {version_row}")
        if not version_row:
            print("FAIL: alembic_version not stamped -- schema was not migrated via Alembic.")
            checks_passed = False

    async with engine.connect() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        coa_count = (
            await conn.execute(text("SELECT count(*) FROM accounts"))
        ).scalar_one()
        print(f"Chart of Accounts rows seeded: {coa_count}")
        if coa_count == 0:
            print("FAIL: expected default Chart of Accounts to be seeded.")
            checks_passed = False

    # -- Cleanup --
    if not keep:
        print(f"\n--- Cleaning up (drop schema {schema}, delete tenant row) ---")
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await conn.execute(text("DELETE FROM public.tenants WHERE id = :id"), {"id": test_tenant_id})
        print("Cleaned up.")
    else:
        print(f"\n--kept-- tenant_id={test_tenant_id} schema={schema} left in place for inspection.")

    print("\n" + "=" * 60)
    if checks_passed:
        print("RESULT: PASS -- tenant provisioning + Alembic migrations work against this real Postgres database.")
    else:
        print("RESULT: FAIL -- see failures above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
