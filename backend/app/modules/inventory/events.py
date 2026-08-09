from decimal import Decimal
from uuid import UUID

from app.core.events.event_bus import DomainEvent


class CogsVarianceAdjustedEvent(DomainEvent):
    event_type: str = "inventory.cogs_variance_adjusted"
    
    tenant_id: UUID
    item_id: UUID
    variant_id: UUID | None
    warehouse_id: UUID
    delta_amount: Decimal
    reason: str


# Register inventory event consumers
import app.modules.inventory.consumers  # noqa: F401, E402
