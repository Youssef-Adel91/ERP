import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.tenancy.migrations import TenantMigrationOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing Tenant Migration Orchestrator...")
    orchestrator = TenantMigrationOrchestrator(concurrency_limit=20)
    
    # Step 1: Run public migrations
    await orchestrator.run_public_migrations()
    
    # Step 2: Fetch tenant schemas (for now, use a dummy list or fetch from DB)
    # Ideally this would query public.tenants
    # dummy_tenants = ["tenant_demo_alpha", "tenant_demo_beta"]
    
    # To demonstrate fetching from DB:
    from sqlalchemy import text

    from app.core.db.database import engine
    
    logger.info("Fetching registered tenant schemas...")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT schema_name FROM public.tenants WHERE status = 'active'"))
            tenant_schemas = [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.warning(f"Could not fetch tenants (maybe table doesn't exist yet): {e}")
        tenant_schemas = []
        
    if not tenant_schemas:
        # Fallback to dummy tenants if we want to force testing the orchestrator
        logger.info("No tenants found in DB. Falling back to dummy schemas for demonstration.")
        tenant_schemas = ["tenant_dummy_test"]
    
    # Pre-create schemas to ensure alembic doesn't fail on missing schemas
    try:
        async with engine.begin() as conn:
            for schema in tenant_schemas:
                await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    except Exception as e:
        logger.warning(f"Could not ensure schemas: {e}")
        
    # Step 3: Run tenant migrations
    await orchestrator.run_tenant_migrations(tenant_schemas)
    logger.info("All migrations finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())
