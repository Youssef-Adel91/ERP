"""
app.modules.logistics.events — Domain Events & Outbox Consumers for Logistics (FR-752, FR-760)

Defines:
  1. CarrierWebhookReceivedEvent: Emitted when a carrier webhook is ingested.
  2. ShipmentStatusUpdatedEvent: Emitted whenever a shipment's canonical state transitions (FR-760).
  3. Consumer handler subscribed to 'logistics.webhook_received' to process webhooks asynchronously.
"""
from __future__ import annotations

import logging

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.logistics.services.shipments import process_shipment_webhook_payload

logger = logging.getLogger(__name__)


class CarrierWebhookReceivedEvent(DomainEvent):
    """Event emitted when a carrier webhook is ingested and passes idempotency check."""

    event_type: str = "logistics.webhook_received"


class ShipmentStatusUpdatedEvent(DomainEvent):
    """
    Event emitted whenever a shipment changes canonical state (FR-760).
    Subscribed to by the Trust Network (Phase 7a) and COD Settlement (Phase 7c) modules.
    """

    event_type: str = "shipment.status_updated"


def register_logistics_event_consumers() -> None:
    """Register logistics event bus consumers."""
    event_bus = get_event_bus()

    @event_bus.subscribe("logistics.webhook_received")
    async def handle_carrier_webhook_received(event: DomainEvent) -> None:
        """
        Asynchronous consumer handler for ingested carrier webhooks.
        Opens a fresh session for the tenant and updates shipment canonical status.
        """
        logger.info(
            "EventBus [logistics.webhook_received]: Processing webhook for tenant='%s'",
            event.tenant_id,
        )
        try:
            async with tenant_session(event.tenant_id) as session:
                await process_shipment_webhook_payload(
                    session=session,
                    tenant_id=event.tenant_id,
                    payload=event.payload,
                )
                await session.commit()
            logger.info("EventBus [logistics.webhook_received]: Successfully processed webhook.")
        except Exception as exc:
            logger.exception(
                "EventBus [logistics.webhook_received]: Error processing webhook for tenant='%s': %s",
                event.tenant_id,
                exc,
            )
            raise


# Register consumers on import
register_logistics_event_consumers()
