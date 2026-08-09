import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, UTC, timedelta

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models.core import (
    Batch,
    Item,
    SerialNumber,
    SerialState,
    StockMovement,
    Warehouse,
)
from app.modules.inventory.services.serial_lifecycle import (
    transition_serial_state,
    validate_sales_return,
    IllegalStateException,
)
from app.modules.inventory.services.costing import consume_stock, CostingRequest


@pytest.fixture
def tenant_session(db_session: AsyncSession):
    return db_session


@pytest.fixture
async def main_warehouse(tenant_session: AsyncSession):
    warehouse = Warehouse(name="Main WH", code="MAIN01")
    tenant_session.add(warehouse)
    await tenant_session.commit()
    return warehouse


@pytest.fixture
async def serialized_item(tenant_session: AsyncSession):
    item = Item(
        sku="PHONE-001",
        name="Smartphone",
        requires_serial=True
    )
    tenant_session.add(item)
    await tenant_session.commit()
    return item


@pytest.fixture
async def batched_item(tenant_session: AsyncSession):
    item = Item(
        sku="MED-001",
        name="Medicine",
        requires_batch=True
    )
    tenant_session.add(item)
    await tenant_session.commit()
    return item


@pytest.mark.asyncio
async def test_serial_state_transitions(tenant_session: AsyncSession, serialized_item: Item):
    serial = SerialNumber(item_id=serialized_item.id, serial_no="SN123", state=SerialState.IN_STOCK)
    tenant_session.add(serial)
    await tenant_session.commit()

    # Valid transition
    updated_serial = await transition_serial_state(tenant_session, serial.id, SerialState.SOLD)
    assert updated_serial.state == SerialState.SOLD

    # Invalid transition (SOLD -> SCRAPPED)
    with pytest.raises(IllegalStateException):
        await transition_serial_state(tenant_session, serial.id, SerialState.SCRAPPED)

    # Valid return
    updated_serial = await transition_serial_state(tenant_session, serial.id, SerialState.RETURNED)
    assert updated_serial.state == SerialState.RETURNED


@pytest.mark.asyncio
async def test_return_fraud_validation(tenant_session: AsyncSession, serialized_item: Item, main_warehouse: Warehouse):
    contact_a = uuid4()
    contact_b = uuid4()

    serial = SerialNumber(item_id=serialized_item.id, serial_no="SN456", state=SerialState.SOLD, current_owner_contact_id=contact_a)
    tenant_session.add(serial)
    await tenant_session.commit()

    # Simulate the outbound movement for Contact A
    movement = StockMovement(
        item_id=serialized_item.id,
        warehouse_id=main_warehouse.id,
        serial_id=serial.id,
        qty=Decimal("-1"),
        movement_type="OUT",
        contact_id=contact_a,
    )
    tenant_session.add(movement)
    await tenant_session.commit()

    # Valid return by Contact A
    is_valid = await validate_sales_return(tenant_session, serial.id, contact_a)
    assert is_valid is True

    # Fraudulent return by Contact B
    with pytest.raises(ValueError, match="Return fraud detected"):
        await validate_sales_return(tenant_session, serial.id, contact_b)


@pytest.mark.asyncio
async def test_strict_capture_validation(tenant_session: AsyncSession, serialized_item: Item, main_warehouse: Warehouse):
    # Try to consume without a serial ID
    req = CostingRequest(
        item_id=serialized_item.id,
        variant_id=None,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("1"),
        movement_type="OUT",
    )
    with pytest.raises(ValueError, match="serial_id is required"):
        await consume_stock(tenant_session, [req])

    # Try to consume with a quantity > 1
    req2 = CostingRequest(
        item_id=serialized_item.id,
        variant_id=None,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("2"),
        movement_type="OUT",
        serial_id=uuid4()
    )
    with pytest.raises(ValueError, match="Quantity must be 1 or -1"):
        await consume_stock(tenant_session, [req2])


@pytest.mark.asyncio
async def test_expiry_hard_block(tenant_session: AsyncSession, batched_item: Item, main_warehouse: Warehouse):
    # Create expired batch
    expired_date = datetime.now(UTC).date() - timedelta(days=1)
    batch = Batch(
        item_id=batched_item.id,
        batch_no="B-EXP",
        expiry_date=expired_date
    )
    tenant_session.add(batch)
    await tenant_session.commit()

    req = CostingRequest(
        item_id=batched_item.id,
        variant_id=None,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("10"),
        movement_type="OUT",
        batch_id=batch.id
    )

    with pytest.raises(ValueError, match="is expired and cannot be consumed"):
        await consume_stock(tenant_session, [req])
