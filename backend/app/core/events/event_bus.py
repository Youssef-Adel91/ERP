"""
app/core/events/event_bus.py — Internal Event Bus (Domain Event Pub/Sub)

Architecture:
  This module implements a dual-backend Event Bus for decoupled communication
  between modules and plugins. The system follows the Observer pattern.

  CRITICAL DESIGN RULE:
    Core modules (accounting, contacts) NEVER import from plugins.
    Plugins NEVER import from core modules.
    ALL cross-module communication goes through this EventBus.

  Backend Selection:
    - "memory" (InMemoryEventBus): Single-process async dispatch. Zero deps.
                                    Suitable for development and testing.
    - "redis"  (RedisEventBus):    Publishes to Redis channel. Celery workers
                                    subscribe and dispatch to handlers.
                                    Required for production and multi-process
                                    deployments.

  Usage:
    # In a plugin (publisher):
    from app.core.events.event_bus import get_event_bus, InvoiceCreatedEvent
    event_bus = get_event_bus()
    await event_bus.publish(InvoiceCreatedEvent(tenant_id="...", payload={...}))

    # In a core module (subscriber):
    from app.core.events.event_bus import get_event_bus
    event_bus = get_event_bus()

    @event_bus.subscribe("invoice.created")
    async def handle_invoice_created(event: DomainEvent) -> None:
        ...
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.context import current_session
from app.modules.system.models import OutboxEvent

logger = logging.getLogger(__name__)


# ── Domain Event Base Model ───────────────────────────────────────────────────


class DomainEvent(BaseModel):
    """
    The universal event envelope for all internal domain events.

    All events flowing through the EventBus must be instances of this class
    or its subclasses. This ensures type safety and a consistent structure.

    Fields:
        event_id:   Unique event ID for deduplication and tracing.
        event_type: String identifier (e.g. "invoice.created", "payment.received").
        tenant_id:  The tenant this event belongs to (critical for data isolation).
        payload:    Arbitrary event-specific data.
        timestamp:  UTC time of event creation.
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    tenant_id: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


# ── Typed Domain Events ───────────────────────────────────────────────────────


class InvoiceCreatedEvent(DomainEvent):
    """Emitted by the Inventory/Invoicing plugin when a new invoice is created."""

    event_type: str = "invoice.created"


class InvoiceOverdueEvent(DomainEvent):
    """Emitted by the Overdue Reminder Engine when an invoice passes its due date."""

    event_type: str = "invoice.overdue"


class PaymentReceivedEvent(DomainEvent):
    """Emitted by the Invoicing plugin when a payment is recorded."""

    event_type: str = "payment.received"


class ContactCreatedEvent(DomainEvent):
    """Emitted when a new contact (customer/supplier) is created."""

    event_type: str = "contact.created"


class TenantProvisionedEvent(DomainEvent):
    """Emitted by the system module after a new tenant schema is ready."""

    event_type: str = "tenant.provisioned"
    tenant_id: str = "system"  # system-level event has no tenant scope


class WhatsAppMessageReceivedEvent(DomainEvent):
    """
    Emitted by app.plugins.whatsapp.api.webhooks.receive_webhook after it
    resolves an inbound Meta webhook's phone_number_id back to a tenant
    (via the public WhatsAppTenantConfig table). tenant_id is therefore
    only known AFTER that lookup — unlike most events, it is not supplied
    by an already-authenticated request.

    Key payload fields:
        phone_number_id, from_number, wa_message_id, message_type,
        text_body (when message_type == "text"), raw_message
    """

    event_type: str = "whatsapp.message_received"


class CaseStageTransitionedEvent(DomainEvent):
    """
    Emitted by the Case Engine on every stage transition.

    Vertical plugins (Recruitment, Hospitality, Rental) subscribe to
    "case.stage.transitioned" and filter on payload["plugin_key"] or
    payload["case_type_code"] to handle only their own transitions.

    Key payload fields:
        case_id, case_type_code, plugin_key,
        from_stage, to_stage, is_terminal,
        resource_id, changed_by, reason
    """

    event_type: str = "case.stage.transitioned"


# ── EventBus Abstract Interface ───────────────────────────────────────────────

HandlerType = Callable[[DomainEvent], Any]


class EventBus:
    """
    EventBus providing Transactional Outbox publishing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[HandlerType]] = {}

    def subscribe(self, event_type: str) -> Callable[[HandlerType], HandlerType]:
        """
        Decorator to register an async handler for a specific event type.

        Example:
            @event_bus.subscribe("invoice.created")
            async def my_handler(event: DomainEvent) -> None:
                ...
        """

        def decorator(func: HandlerType) -> HandlerType:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(func)
            logger.debug(
                "Registered handler '%s' for event type '%s'",
                func.__name__,
                event_type,
            )
            return func

        return decorator

    def get_handlers(self, event_type: str) -> list[HandlerType]:
        """Return all registered handlers for a given event type."""
        return self._subscribers.get(event_type, [])

    async def publish(self, event: DomainEvent, session: AsyncSession | None = None) -> None:
        """
        Publish a domain event via the Transactional Outbox pattern.
        
        If no session is provided, it attempts to fetch the ambient session
        using `current_session.get()`. It creates an `OutboxEvent` and calls `session.add()`.
        It does NOT call `commit()`.
        """
        sess = session or current_session.get()
        if not sess:
            raise RuntimeError("EventBus.publish requires an active AsyncSession.")
            
        # The aggregate_id is not strictly typed in DomainEvent yet, but we 
        # can default to tenant_id or a system UUID if not present.
        aggregate_id = event.payload.get("id") or getattr(event, "aggregate_id", None) or UUID("00000000-0000-0000-0000-000000000000")
        if isinstance(aggregate_id, str):
            try:
                aggregate_id = UUID(aggregate_id)
            except ValueError:
                aggregate_id = UUID("00000000-0000-0000-0000-000000000000")
        
        tenant_id = UUID("00000000-0000-0000-0000-000000000000") if event.tenant_id == "system" else UUID(event.tenant_id)
                
        outbox_event = OutboxEvent(
            tenant_id=tenant_id,
            aggregate_type=event.event_type.split(".")[0],
            aggregate_id=aggregate_id,
            event_type=event.event_type,
            payload=event.model_dump(mode="json"),
        )
        sess.add(outbox_event)

# ── Singleton Instance & Factory ──────────────────────────────────────────────

_bus_instance: EventBus | None = None


def _create_event_bus() -> EventBus:
    """Create the EventBus."""
    return EventBus()


def get_event_bus() -> EventBus:
    """
    FastAPI dependency / module-level accessor for the EventBus singleton.

    The same instance is returned throughout the application lifecycle.
    All module handlers registered via @event_bus.subscribe() at import
    time are attached to this instance.
    """
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = _create_event_bus()
    return _bus_instance
