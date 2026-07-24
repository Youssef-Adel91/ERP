"""
app/core/event_bus.py — Internal Event Bus (Domain Event Pub/Sub)

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
    from app.core.event_bus import get_event_bus, InvoiceCreatedEvent
    event_bus = get_event_bus()
    await event_bus.publish(InvoiceCreatedEvent(tenant_id="...", payload={...}))

    # In a core module (subscriber):
    from app.core.event_bus import get_event_bus
    event_bus = get_event_bus()

    @event_bus.subscribe("invoice.created")
    async def handle_invoice_created(event: DomainEvent) -> None:
        ...
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from app.core.config import settings

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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"json_encoders": {UUID: str, datetime: lambda v: v.isoformat()}}


# ── Typed Domain Events ───────────────────────────────────────────────────────


class InvoiceCreatedEvent(DomainEvent):
    """Emitted by the Inventory/Invoicing plugin when a new invoice is created."""

    event_type: str = "invoice.created"


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


# ── EventBus Abstract Interface ───────────────────────────────────────────────

HandlerType = Callable[[DomainEvent], Any]


class EventBus(ABC):
    """
    Abstract base class defining the EventBus interface.
    All backends must implement publish().
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

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to all registered subscribers."""
        ...


# ── Backend 1: In-Memory (MVP / Testing) ─────────────────────────────────────


class InMemoryEventBus(EventBus):
    """
    Single-process, in-memory event dispatcher using asyncio tasks.

    Handlers are invoked as fire-and-forget asyncio tasks, meaning the
    publisher is NOT blocked by handler execution time.

    ⚠️  NOT suitable for multi-process deployments. Events are lost on restart.
        Use RedisEventBus for production.
    """

    async def publish(self, event: DomainEvent) -> None:
        handlers = self.get_handlers(event.event_type)

        if not handlers:
            logger.debug(
                "No handlers registered for event '%s' (tenant: %s)",
                event.event_type,
                event.tenant_id,
            )
            return

        logger.info(
            "Publishing event '%s' (id=%s, tenant=%s) to %d handler(s)",
            event.event_type,
            event.event_id,
            event.tenant_id,
            len(handlers),
        )

        for handler in handlers:
            # Schedule as an asyncio task — non-blocking for the publisher
            asyncio.create_task(
                _safe_handler_call(handler, event),
                name=f"event_{event.event_type}_{event.event_id}",
            )


async def _safe_handler_call(handler: HandlerType, event: DomainEvent) -> None:
    """Execute a handler and catch any exceptions to prevent bus crashes."""
    try:
        await handler(event)
    except Exception:
        logger.exception(
            "Unhandled exception in event handler '%s' for event '%s' (id=%s)",
            handler.__name__,
            event.event_type,
            event.event_id,
        )


# ── Backend 2: Redis Pub/Sub (Production) ─────────────────────────────────────


class RedisEventBus(EventBus):
    """
    Production event bus using Redis Pub/Sub.

    The publisher serializes the DomainEvent to JSON and publishes it to a
    Redis channel. A separate Celery worker process subscribes to the channel
    and dispatches events to the appropriate handlers.

    This backend supports:
      - Multi-process deployments (scale horizontally)
      - Event persistence (via Celery task queue)
      - Dead-letter queues (failed handlers → Celery retry)
      - Event replay (via Celery beat or manual re-queue)
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__()
        self.redis = redis
        self.channel = settings.REDIS_CHANNEL

    async def publish(self, event: DomainEvent) -> None:
        """
        Serialize the DomainEvent to JSON and publish to Redis channel.
        The Celery worker (`app/workers/event_consumer.py`) receives and
        dispatches this to the registered Python handlers.
        """
        event_json = event.model_dump_json()
        subscribers_count = await self.redis.publish(self.channel, event_json)

        logger.info(
            "Published event '%s' (id=%s) to Redis channel '%s' → %d subscriber(s)",
            event.event_type,
            event.event_id,
            self.channel,
            subscribers_count,
        )


# ── Singleton Instance & Factory ──────────────────────────────────────────────

_bus_instance: EventBus | None = None


def _create_event_bus() -> EventBus:
    """Create the appropriate EventBus backend based on configuration."""
    if settings.EVENT_BUS_BACKEND == "redis":
        from app.core.database import redis_client
        return RedisEventBus(redis=redis_client)
    return InMemoryEventBus()


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
