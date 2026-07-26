"""
app/core/event_bus.py — Backwards-Compatibility Shim

This file re-exports everything from the new canonical location:
    app.core.events.event_bus

It exists so that legacy imports like:
    from app.core.event_bus import get_event_bus, DomainEvent
continue to work without modification in alembic/env.py and tests.

New code SHOULD import directly from:
    from app.core.events.event_bus import ...
"""
from app.core.events.event_bus import (  # noqa: F401
    ContactCreatedEvent,
    DomainEvent,
    EventBus,
    HandlerType,
    InvoiceCreatedEvent,
    PaymentReceivedEvent,
    TenantProvisionedEvent,
    _bus_instance,
    _create_event_bus,
    get_event_bus,
)
