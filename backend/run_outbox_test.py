import asyncio
import os
from uuid import uuid4

# Ensure we use Postgres, not SQLite
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@db:5432/omni_erp"
os.environ["REDIS_URL"] = "redis://redis:6379/0"

from sqlalchemy import select

from app.core.db.context import current_session
from app.core.db.database import AsyncSessionLocal, redis_client
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.events.relay import relay_tick
from app.modules.system.models import OutboxEvent


class DummyEvent(DomainEvent):
    event_type: str = "dummy.created"

async def main():
    print("Starting test_crash_between_commit_and_dispatch_loses_nothing...")
    tenant_id = uuid4()
    
    # Simulate a business logic transaction publishing an event
    async with AsyncSessionLocal() as session:
        current_session.set(session)
        
        bus = get_event_bus()
        event = DummyEvent(tenant_id=str(tenant_id), payload={"id": str(uuid4()), "message": "hello"})
        
        # Publish event - inserts OutboxEvent into DB without committing
        await bus.publish(event)
        
        # We explicitly commit, simulating a successful DB transaction
        await session.commit()
        current_session.set(None)
        
    print("Event committed to DB. Simulating crash... (not sending to Redis)")
    
    # Now the Relay tick runs
    print("Running relay_tick...")
    relayed_count = await relay_tick(redis_client)
    assert relayed_count >= 1, "Relay tick failed to pick up the event"
    
    # Verify the event is now marked as published in the DB
    async with AsyncSessionLocal() as session:
        stmt = select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id)
        result = await session.execute(stmt)
        outbox_event = result.scalars().first()
        assert outbox_event is not None
        assert outbox_event.published_at is not None, "Event not marked as published in DB"
        
    # Verify the event was actually written to Redis Streams
    stream_key = f"events:stream:{outbox_event.aggregate_id}"
    messages = await redis_client.xrange(stream_key)
    assert len(messages) >= 1, "Event not found in Redis Stream"
    
    # Clean up the stream
    await redis_client.delete(stream_key)
    
    print("SUCCESS: test_crash_between_commit_and_dispatch_loses_nothing passed!")

if __name__ == "__main__":
    asyncio.run(main())
