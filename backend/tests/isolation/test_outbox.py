from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.db.context import current_session
from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.events.relay import relay_tick
from app.modules.system.models import OutboxEvent


class DummyEvent(DomainEvent):
    event_type: str = "dummy.created"
    
@pytest.mark.asyncio
async def test_crash_between_commit_and_dispatch_loses_nothing(redis_client):
    """
    Test that if an event is published and committed to the database, but the process
    crashes before it can be dispatched to Redis, the relay task will pick it up
    and dispatch it.
    """
    tenant_id = uuid4()
    
    # Simulate a business logic transaction publishing an event
    async with tenant_session(tenant_id) as session:
        current_session.set(session)
        
        bus = get_event_bus()
        event = DummyEvent(tenant_id=str(tenant_id), payload={"id": str(uuid4()), "message": "hello"})
        
        # Publish event - inserts OutboxEvent into DB without committing
        await bus.publish(event)
        
        # We explicitly commit, simulating a successful DB transaction
        await session.commit()
        current_session.set(None)
        
    # Simulate a crash right after commit (the event is in DB, but not in Redis)
    # Now the Relay tick runs
    relayed_count = await relay_tick(redis_client)
    assert relayed_count >= 1
    
    # Verify the event is now marked as published in the DB
    async with tenant_session(tenant_id) as session:
        stmt = select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id)
        result = await session.execute(stmt)
        outbox_event = result.scalars().first()
        assert outbox_event is not None
        assert outbox_event.published_at is not None
        
    # Verify the event was actually written to Redis Streams
    stream_key = f"events:stream:{outbox_event.aggregate_id}"
    messages = await redis_client.xrange(stream_key)
    assert len(messages) >= 1
    
    # Clean up the stream
    await redis_client.delete(stream_key)
