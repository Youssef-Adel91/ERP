import logging
from collections.abc import Callable
from functools import wraps
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from app.core.db.context import current_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.core.models import ProcessedEvent

logger = logging.getLogger(__name__)

def consumer(event_type: str, name: str) -> Callable:
    """
    Decorator for idempotent event consumers.
    Wraps the handler in a block that attempts to INSERT into ProcessedEvent.
    """
    def decorator(func: Callable[[DomainEvent], Any]) -> Callable[[DomainEvent], Any]:
        @wraps(func)
        async def wrapper(event: DomainEvent, *args, **kwargs) -> Any:
            session = current_session.get()
            if not session:
                raise RuntimeError("Consumer requires an active AsyncSession.")
            
            # Convert event.event_id to UUID if necessary
            event_id = event.event_id
            if isinstance(event_id, str):
                event_id = UUID(event_id)
                
            try:
                # Attempt to insert into ProcessedEvent
                # Note: ProcessedEvent is in the tenant schema, so the session
                # must be configured with the correct tenant schema_translate_map
                stmt = insert(ProcessedEvent).values(
                    consumer_name=name,
                    event_id=event_id,
                ).on_conflict_do_nothing()
                
                result = await session.execute(stmt)
                if result.rowcount == 0:
                    logger.debug(f"Event {event_id} already processed by {name}, skipping.")
                    return None
                    
                # If insert succeeded, run the handler
                return await func(event, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error in consumer {name} for event {event_id}: {e}")
                raise
                
        # Register with the EventBus
        bus = get_event_bus()
        bus.subscribe(event_type)(wrapper)
        
        return wrapper
    return decorator
