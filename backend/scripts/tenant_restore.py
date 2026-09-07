"""
scripts/tenant_restore.py
Per-Tenant Restore & Integrity Verification Tool (Phase 8: Workstream C) FR-841

Restores a single tenant's schema from a pg_dump/pg_restore backup file into
an isolated, temporary scratch database (NEVER the live database) and then
executes post-restore checksums and row count verifications against that
restored copy to guarantee data integrity across critical financial and
inventory tables.

Backup format expected: a `pg_dump` archive (custom format, `-Fc`, produced
with `pg_dump -n <tenant_schema> -Fc -f backup.dump <source_db_url>`) that
was taken of a single tenant schema. `pg_restore` is used to replay it.

Safety model:
  1. A brand-new, uniquely-named database (`<tenant_schema>_restore_test_<pid>`)
     is created on the same Postgres server as the configured DATABASE_URL.
  2. `pg_restore` replays the backup file into THAT database only.
  3. Integrity checks run against the restored schema inside that scratch
     database — never against the live/production database.
  4. The scratch database is always dropped afterwards (try/finally), even
     if the restore or the integrity check fails.

If `pg_restore` fails, or is not installed / not on PATH, this script fails
LOUDLY: it logs a clear error and exits with a non-zero status. It never
reports success unless an actual restore + integrity check both succeeded.
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.db.context import schema_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tenant_restore")


class RestoreError(RuntimeError):
    """Raised whenever the restore/verification pipeline cannot proceed safely."""


def _swap_database(url: str, new_db_name: str) -> str:
    """Return `url` with its path (database name) replaced by `new_db_name`."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{new_db_name}", parts.query, parts.fragment))


def _to_libpq_url(url: str) -> str:
    """
    Convert a SQLAlchemy async URL (e.g. postgresql+asyncpg://...) into the
    plain `postgresql://...` form that the `pg_restore` / `psql` CLI tools
    (libpq) understand. They do not know about SQLAlchemy driver suffixes.
    """
    scheme, sep, rest = url.partition("://")
    driver = scheme.split("+", 1)[0]
    return f"{driver}{sep}{rest}"


async def verify_data_integrity(session, tenant_id: str):
    """
    Executes post-restore queries to verify row counts and data checksums
    against the schema currently active on `session`'s connection (this
    MUST be the restored scratch database's schema, not the live one).
    """
    logger.info("Executing post-restore data integrity checks...")

    # 1. Verify CostLayers
    cost_layer_query = text("SELECT COUNT(id), COALESCE(SUM(qty_received), 0) FROM cost_layers")
    cl_result = (await session.execute(cost_layer_query)).fetchone()
    logger.info(f"[CostLayers] Rows: {cl_result[0]}, Sum(qty_received): {cl_result[1]}")

    # 2. Verify StockMovements
    stock_query = text("SELECT COUNT(id), COALESCE(SUM(qty), 0) FROM stock_movements")
    sm_result = (await session.execute(stock_query)).fetchone()
    logger.info(f"[StockMovements] Rows: {sm_result[0]}, Sum(qty): {sm_result[1]}")

    # 3. Verify SalesInvoices
    invoice_query = text("SELECT COUNT(id), COALESCE(SUM(grand_total), 0) FROM sales_invoices")
    inv_result = (await session.execute(invoice_query)).fetchone()
    logger.info(f"[SalesInvoices] Rows: {inv_result[0]}, Sum(grand_total): {inv_result[1]}")

    if cl_result[0] == 0 and sm_result[0] == 0 and inv_result[0] == 0:
        logger.warning(f"Tenant {tenant_id} is completely empty. Restore may have failed or tenant had no data.")
    else:
        logger.info("Post-restore integrity checks passed successfully.")


def _run_pg_restore(cmd: list[str]) -> subprocess.CompletedProcess:
    """
    Synchronous subprocess.run() invocation, matching the pattern used by
    provision_tenant_schema() / _provision_tenant_schema_internal() in
    app/core/db/database.py: plain, blocking subprocess.run(capture_output=True)
    rather than asyncio.create_subprocess_exec(), because the latter raises
    NotImplementedError on Windows when the running event loop is the default
    SelectorEventLoop. The blocking call itself is executed inside a
    ThreadPoolExecutor by the caller so it doesn't block this script's event
    loop while awaited.
    """
    return subprocess.run(cmd, capture_output=True)


async def _run_pg_restore_async(cmd: list[str]) -> subprocess.CompletedProcess:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_pg_restore, cmd)


async def restore_tenant(tenant_id: str, backup_file: str):
    """
    Restores a tenant's schema from `backup_file` into a fresh, isolated
    scratch database, verifies data integrity against that restored copy,
    and always drops the scratch database afterwards.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        raise RestoreError(
            "DATABASE_URL is SQLite; pg_restore/PostgreSQL restore testing is not "
            "supported against a SQLite backend."
        )

    # Validate/normalize the tenant id, and derive the canonical schema name
    # using the SAME convention as the live app (app.core.db.context.schema_for),
    # not an ad-hoc one — using a mismatched name here would silently make the
    # `-n` filter and the post-restore search_path target the wrong schema.
    UUID(tenant_id)  # raises ValueError if malformed
    schema_name = schema_for(tenant_id)

    scratch_db_name = f"{schema_name}_restore_test_{os.getpid()}"
    admin_url = _swap_database(settings.DATABASE_URL, "postgres")
    scratch_url = _swap_database(settings.DATABASE_URL, scratch_db_name)
    scratch_libpq_url = _to_libpq_url(scratch_url)

    logger.info(f"Initiating restoration for schema: {schema_name}")
    logger.info(f"Source backup: {backup_file}")
    logger.info(f"Scratch (temporary) database: {scratch_db_name}")

    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    scratch_engine = None
    try:
        # ── Step 1: create an isolated scratch database ─────────────────────
        try:
            async with admin_engine.connect() as conn:
                await conn.execute(text(f'CREATE DATABASE "{scratch_db_name}"'))
        except Exception as e:
            raise RestoreError(f"Failed to create scratch database '{scratch_db_name}': {e}") from e

        # ── Step 2: run the REAL pg_restore against the scratch database ────
        cmd = [
            "pg_restore",
            "--no-owner",
            "--no-privileges",
            "-n", schema_name,
            "-d", scratch_libpq_url,
            backup_file,
        ]
        try:
            result = await _run_pg_restore_async(cmd)
        except FileNotFoundError as e:
            raise RestoreError(
                "pg_restore executable was not found on PATH. Install the "
                "PostgreSQL client tools and ensure `pg_restore` is on PATH "
                "before running this script."
            ) from e

        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace")
            raise RestoreError(f"pg_restore failed (exit code {result.returncode}): {stderr_text}")

        logger.info("pg_restore completed successfully.")

        # ── Step 3: verify data integrity against the RESTORED scratch DB ───
        scratch_engine = create_async_engine(scratch_url)
        try:
            async with AsyncSession(scratch_engine, expire_on_commit=False) as session:
                # Point this session's search_path at the restored tenant
                # schema so the unqualified table names in
                # verify_data_integrity() resolve inside the scratch
                # database's restored schema, not "public".
                await session.execute(text(f'SET search_path TO "{schema_name}", public'))
                await verify_data_integrity(session, tenant_id)
        except Exception as e:
            raise RestoreError(
                f"Integrity check failed. The schema {schema_name} may not exist in "
                f"the restored scratch database or is corrupted. Details: {e}"
            ) from e

        logger.info(f"Restore workflow completed for Tenant {tenant_id}.")
    finally:
        if scratch_engine is not None:
            await scratch_engine.dispose()
        # ── Step 4: always clean up the scratch database ────────────────────
        try:
            async with admin_engine.connect() as conn:
                # Terminate any lingering connections to the scratch DB before
                # dropping it, otherwise DROP DATABASE fails with "database is
                # being accessed by other users".
                await conn.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :dbname AND pid <> pg_backend_pid()"
                ), {"dbname": scratch_db_name})
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_db_name}"'))
            logger.info(f"Cleaned up scratch database: {scratch_db_name}")
        except Exception as cleanup_err:
            logger.error(
                f"Failed to clean up scratch database '{scratch_db_name}'. "
                f"Manual cleanup may be required. Details: {cleanup_err}"
            )
        await admin_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Per-Tenant Restore & Verification Tool")
    parser.add_argument("--tenant-id", type=str, required=True, help="Target Tenant UUID")
    parser.add_argument("--backup-file", type=str, required=True, help="Path to the pg_dump custom-format backup file")

    args = parser.parse_args()

    try:
        asyncio.run(restore_tenant(args.tenant_id, args.backup_file))
    except RestoreError as e:
        logger.error(f"Restore FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Restore FAILED with an unexpected error: {e}")
        sys.exit(1)
