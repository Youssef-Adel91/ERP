"""
app/plugins/inventory/events.py — Inventory EventBus Handlers

Listens for core events (like tenant.provisioned) to initialize plugin-specific
data, such as creating the default Main Warehouse.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.event_bus import DomainEvent, get_event_bus
from app.plugins.inventory.models import Warehouse

logger = logging.getLogger(__name__)

event_bus = get_event_bus()


async def _tenant_session(tenant_id: str) -> AsyncSession:
    """Create an AsyncSession scoped to a specific tenant schema."""
    schema_name = f"tenant_{tenant_id.replace('-', '_')}"
    session = AsyncSessionLocal()
    await session.execute(text(f'SET search_path TO "{schema_name}", public'))
    return session


@event_bus.subscribe("tenant.provisioned")
async def handle_tenant_provisioned_inventory(event: DomainEvent) -> None:
    """
    Listen for `tenant.provisioned` and create a default Main Warehouse
    for the newly registered tenant.
    """
    event_id_str = str(event.event_id)
    payload = event.payload
    tenant_id = payload.get("tenant_id")
    
    if not tenant_id:
        logger.error(
            "❌ handle_tenant_provisioned_inventory aborted (event_id=%s): missing tenant_id in payload",
            event_id_str,
        )
        return

    logger.info(
        "📥 Received tenant.provisioned in Inventory plugin (event_id=%s, tenant=%s). Creating default warehouse.",
        event_id_str,
        tenant_id,
    )

    session = await _tenant_session(tenant_id)
    try:
        warehouse = Warehouse(
            name="Main Warehouse",
            name_ar="المخزن الرئيسي",
            location="Headquarters",
            is_default=True,
        )
        session.add(warehouse)
        await session.commit()
        
        logger.info(
            "✅ Default Main Warehouse created for tenant '%s'",
            tenant_id,
        )
    except Exception:
        await session.rollback()
        logger.exception(
            "❌ DB error while processing tenant.provisioned in Inventory (event_id=%s, tenant=%s)",
            event_id_str,
            tenant_id,
        )
        raise
    finally:
        await session.close()
