"""
tests/test_event_bus.py — EventBus Pub/Sub Round-Trip Tests
"""
from __future__ import annotations

import pytest

from app.core.event_bus import DomainEvent, EventBus


@pytest.mark.asyncio
class TestEventBus:

    async def test_subscribe_registers_handler(self):
        """Handler registered with @subscribe should be added to the registry."""
        bus = EventBus()

        @bus.subscribe("test.event")
        async def handler(event: DomainEvent) -> None:
            pass

        handlers = bus.get_handlers("test.event")
        assert len(handlers) == 1
        assert handlers[0] == handler

    async def test_publish_inserts_outbox_event(self, db_session):
        """Publishing an event should insert an OutboxEvent into the session without committing."""
        from sqlalchemy import select

        from app.core.db.context import current_session
        from app.modules.system.models import OutboxEvent

        bus = EventBus()
        current_session.set(db_session)

        event = DomainEvent(
            event_type="test.event",
            tenant_id="00000000-0000-0000-0000-000000000000",
            payload={"message": "hello"},
        )
        await bus.publish(event)
        
        # Check that OutboxEvent is pending in session
        assert len(db_session.new) == 1
        
        # We explicitly commit to verify DB constraints
        await db_session.commit()
        
        # Query it back
        stmt = select(OutboxEvent).where(OutboxEvent.event_type == "test.event")
        result = await db_session.execute(stmt)
        outbox_event = result.scalars().first()
        
        assert outbox_event is not None
        assert outbox_event.payload["payload"] == {"message": "hello"}
        
        current_session.set(None)
