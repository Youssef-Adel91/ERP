"""
app/plugins/inventory/events.py — Inventory EventBus Handlers

Listens for core events (like tenant.provisioned) to initialize plugin-specific
data, such as creating the default Main Warehouse.
"""

import logging

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus

try:
    from app.plugins.inventory.models import Warehouse
except ImportError:
    Warehouse = None  # type: ignore[assignment,misc]  # Model not yet created

logger = logging.getLogger(__name__)

event_bus = get_event_bus()




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

    async with tenant_session(tenant_id) as session:
        try:
            if Warehouse is None:
                logger.warning(
                    "⚠️  Warehouse model not available — skipping default warehouse creation for tenant '%s'",
                    tenant_id,
                )
                return
            warehouse = Warehouse(
                name="Main Warehouse",
                name_ar="المخزن الرئيسي",
                location="Headquarters",
                is_default=True,
            )
            session.add(warehouse)
            
            logger.info(
                "✅ Default Main Warehouse created for tenant '%s'",
                tenant_id,
            )
        except Exception:
            logger.exception(
                "❌ DB error while processing tenant.provisioned in Inventory (event_id=%s, tenant=%s)",
                event_id_str,
                tenant_id,
            )
            raise
