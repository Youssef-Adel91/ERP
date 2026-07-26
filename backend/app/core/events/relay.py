import json
import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.db.database import public_session
from app.modules.system.models import OutboxEvent

logger = logging.getLogger(__name__)

async def relay_tick(redis: Redis) -> int:
    """
    Reads unpublished OutboxEvents from the database, publishes them to Redis,
    and marks them as published. Returns the number of events relayed.
    """
    relayed_count = 0
    async with public_session() as session:
        # Query up to 200 unpublished events, ordered by occurrence
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.occurred_at)
            .limit(200)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()
        
        for event in events:
            # Publish to Redis using xadd
            # Partition by aggregate_id to guarantee ordering per aggregate
            stream_key = f"events:stream:{event.aggregate_id}"
            
            # xadd requires fields to be strings/bytes
            fields = {
                "event_id": str(event.id),
                "tenant_id": str(event.tenant_id),
                "event_type": event.event_type,
                "payload": json.dumps(event.payload),
            }
            
            await redis.xadd(stream_key, fields)
            
            event.published_at = datetime.now(UTC)
            relayed_count += 1
            
        if relayed_count > 0:
            await session.commit()
            
    return relayed_count
