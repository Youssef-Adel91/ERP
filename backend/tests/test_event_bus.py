"""
tests/test_event_bus.py — EventBus Pub/Sub Round-Trip Tests
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.core.event_bus import DomainEvent, InMemoryEventBus


@pytest.mark.asyncio
class TestInMemoryEventBus:

    async def test_subscribe_and_publish_round_trip(self):
        """Handler registered with @subscribe should be called on publish."""
        bus = InMemoryEventBus()
        received: list[DomainEvent] = []

        @bus.subscribe("test.event")
        async def handler(event: DomainEvent) -> None:
            received.append(event)

        event = DomainEvent(
            event_type="test.event",
            tenant_id="tenant-001",
            payload={"message": "hello"},
        )
        await bus.publish(event)

        # Give asyncio tasks time to execute
        await asyncio.sleep(0.01)

        assert len(received) == 1
        assert received[0].payload["message"] == "hello"
        assert received[0].tenant_id == "tenant-001"

    async def test_multiple_handlers_all_called(self):
        """Multiple handlers for the same event type should all be called."""
        bus = InMemoryEventBus()
        call_log: list[str] = []

        @bus.subscribe("multi.event")
        async def handler_a(event: DomainEvent) -> None:
            call_log.append("A")

        @bus.subscribe("multi.event")
        async def handler_b(event: DomainEvent) -> None:
            call_log.append("B")

        await bus.publish(
            DomainEvent(event_type="multi.event", tenant_id="t1", payload={})
        )
        await asyncio.sleep(0.01)

        assert set(call_log) == {"A", "B"}

    async def test_no_handlers_does_not_raise(self):
        """Publishing to an event type with no handlers should not raise."""
        bus = InMemoryEventBus()
        await bus.publish(
            DomainEvent(event_type="orphan.event", tenant_id="t1", payload={})
        )  # Should complete without exception

    async def test_failing_handler_does_not_crash_bus(self):
        """An exception in one handler should not prevent others from executing."""
        bus = InMemoryEventBus()
        results: list[str] = []

        @bus.subscribe("crash.event")
        async def bad_handler(event: DomainEvent) -> None:
            raise RuntimeError("Intentional failure in test")

        @bus.subscribe("crash.event")
        async def good_handler(event: DomainEvent) -> None:
            results.append("good_handler_ran")

        await bus.publish(
            DomainEvent(event_type="crash.event", tenant_id="t1", payload={})
        )
        await asyncio.sleep(0.05)

        # good_handler should still run despite bad_handler failing
        assert "good_handler_ran" in results

    async def test_event_tenant_isolation(self):
        """Events should carry tenant context in the payload."""
        bus = InMemoryEventBus()
        received_tenants: list[str] = []

        @bus.subscribe("tenant.event")
        async def handler(event: DomainEvent) -> None:
            received_tenants.append(event.tenant_id)

        for tenant_id in ["tenant-A", "tenant-B", "tenant-C"]:
            await bus.publish(
                DomainEvent(event_type="tenant.event", tenant_id=tenant_id, payload={})
            )

        await asyncio.sleep(0.05)

        assert received_tenants == ["tenant-A", "tenant-B", "tenant-C"]

    async def test_event_has_unique_id(self):
        """Each published event should have a unique event_id."""
        bus = InMemoryEventBus()
        ids: list = []

        @bus.subscribe("id.event")
        async def handler(event: DomainEvent) -> None:
            ids.append(event.event_id)

        for _ in range(5):
            await bus.publish(
                DomainEvent(event_type="id.event", tenant_id="t1", payload={})
            )

        await asyncio.sleep(0.05)

        assert len(set(ids)) == 5  # All IDs must be unique
