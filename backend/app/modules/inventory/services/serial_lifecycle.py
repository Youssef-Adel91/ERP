from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.modules.inventory.models.core import SerialNumber, SerialState, StockMovement

class IllegalStateException(ValueError):
    pass

# Define valid state transitions
VALID_TRANSITIONS = {
    SerialState.IN_STOCK: {SerialState.RESERVED, SerialState.SOLD, SerialState.SCRAPPED, SerialState.UNDER_REPAIR},
    SerialState.RESERVED: {SerialState.IN_STOCK, SerialState.SOLD},
    SerialState.SOLD: {SerialState.RETURNED},
    SerialState.RETURNED: {SerialState.IN_STOCK, SerialState.SCRAPPED, SerialState.UNDER_REPAIR},
    SerialState.SCRAPPED: set(),
    SerialState.UNDER_REPAIR: {SerialState.IN_STOCK, SerialState.SCRAPPED},
}

async def transition_serial_state(
    session: AsyncSession,
    serial_id: UUID,
    new_state: SerialState,
    contact_id: UUID | None = None
) -> SerialNumber:
    """
    Transitions a serial number to a new state if valid.
    Optionally updates the current owner if provided.
    """
    serial = await session.get(SerialNumber, serial_id)
    if not serial:
        raise ValueError(f"Serial number {serial_id} not found")

    allowed_states = VALID_TRANSITIONS.get(serial.state, set())
    if new_state not in allowed_states:
        raise IllegalStateException(
            f"Cannot transition serial {serial_id} from {serial.state} to {new_state}"
        )

    serial.state = new_state
    
    if contact_id is not None:
        serial.current_owner_contact_id = contact_id
    elif new_state in (SerialState.RETURNED, SerialState.IN_STOCK, SerialState.SCRAPPED, SerialState.UNDER_REPAIR):
        # Clear owner when returning to internal control
        serial.current_owner_contact_id = None

    session.add(serial)
    return serial


async def validate_sales_return(
    session: AsyncSession,
    serial_id: UUID,
    returning_contact_id: UUID
) -> bool:
    """
    Validates a sales return to prevent return fraud (FR-345).
    Ensures the serial is currently SOLD and was sold to the specific customer attempting the return.
    """
    serial = await session.get(SerialNumber, serial_id)
    if not serial:
        raise ValueError(f"Serial number {serial_id} not found")

    if serial.state != SerialState.SOLD:
        raise ValueError(f"Serial {serial_id} is in state {serial.state}, cannot be returned")

    # Find the most recent outbound movement for this serial
    stmt = (
        select(StockMovement)
        .where(
            StockMovement.serial_id == serial_id,
            StockMovement.movement_type.in_(["OUT", "SALES_ISSUE"])
        )
        .order_by(desc(StockMovement.occurred_at))
        .limit(1)
    )
    result = await session.execute(stmt)
    last_outbound = result.scalar_one_or_none()

    if not last_outbound:
        raise ValueError(f"No previous outbound movement found for serial {serial_id}")

    if last_outbound.contact_id != returning_contact_id:
        raise ValueError(
            f"Return fraud detected: Serial {serial_id} was not sold to contact {returning_contact_id}"
        )

    return True
