import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/ — the directory containing alembic.ini. Subprocess calls below
# MUST run with this as cwd, since alembic.ini's [tenant]/[public] sections
# use paths (script_location = alembic/tenant) relative to it.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class TenantMigrationOrchestrator:
    """
    Orchestrates Alembic migrations for public and tenant schemas.
    Executes tenant schemas concurrently using subprocesses to avoid Alembic state retention.
    """

    def __init__(self, concurrency_limit: int = 20):
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def run_public_migrations(self) -> None:
        """Run migrations on the public schema synchronously using subprocess."""
        logger.info("Executing public schema migrations...")
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", "-n", "public", "upgrade", "head",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_BACKEND_ROOT,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"Public migration failed:\n{stderr.decode()}")
            raise RuntimeError(f"Public migration failed: {stderr.decode()}")
        logger.info(f"Public migration completed successfully.\n{stdout.decode()}")

    async def _migrate_tenant(self, schema_name: str) -> None:
        """Helper to run a single tenant's migration."""
        async with self.semaphore:
            logger.info(f"Executing migration for tenant schema: {schema_name}...")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "alembic", "-n", "tenant", "-x", f"schema={schema_name}", "upgrade", "head",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=_BACKEND_ROOT,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                logger.error(f"Tenant {schema_name} migration failed:\n{stderr.decode()}")
                raise RuntimeError(f"Tenant {schema_name} migration failed: {stderr.decode()}")
            logger.info(f"Tenant {schema_name} migration completed successfully.")

    async def stamp_tenant(self, schema_name: str) -> None:
        """
        Marks a tenant schema as already being at the latest migration
        revision WITHOUT running any DDL. For backfilling tenants that were
        provisioned via the old create_all() path (so their tables already
        exist but they have no alembic_version row) — run this ONCE per
        pre-existing tenant before switching provisioning over to
        _migrate_tenant, otherwise the next real migration will try to
        recreate tables that already exist and fail.
        """
        async with self.semaphore:
            logger.info(f"Stamping tenant schema {schema_name} as head (no DDL)...")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "alembic", "-n", "tenant", "-x", f"schema={schema_name}", "stamp", "head",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=_BACKEND_ROOT,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                logger.error(f"Tenant {schema_name} stamp failed:\n{stderr.decode()}")
                raise RuntimeError(f"Tenant {schema_name} stamp failed: {stderr.decode()}")
            logger.info(f"Tenant {schema_name} stamped at head successfully.")

    async def run_tenant_migrations(self, schemas: list[str]) -> None:
        """Execute migrations concurrently for all provided tenant schemas."""
        if not schemas:
            logger.info("No tenant schemas provided for migration.")
            return

        logger.info(f"Planning migrations for {len(schemas)} tenant schemas...")
        tasks = [self._migrate_tenant(schema) for schema in schemas]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        failures = [r for r in results if isinstance(r, Exception)]
        if failures:
            logger.error(f"{len(failures)} tenant migrations failed.")
            # Depending on strictness, we might want to raise here
            raise RuntimeError(f"Migration failures detected: {failures}")
        logger.info(f"All {len(schemas)} tenant migrations completed successfully.")
