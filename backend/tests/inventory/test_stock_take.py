import pytest
from uuid import uuid4
from decimal import Decimal

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import (
    Item,
    StockLevel,
    Warehouse,
    CostLayer,
    StockMovement,
    StockTake,
    StockTakeStatus,
    StockTakeLine,
)
from app.modules.inventory.services.stock_take import (
    start_count,
    get_blind_count_sheet,
    record_count,
    post_stock_take,
)
from app.modules.system.models import OutboxEvent

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
async def base_item(tenant_session: AsyncSession):
    item = Item(sku="ITEM-ST", name="Stock Take Item")
    tenant_session.add(item)
    await tenant_session.commit()
    return item


@pytest.mark.asyncio
async def test_stock_take_full_cycle(tenant_session: AsyncSession, base_item: Item, main_warehouse: Warehouse):
    # 1. Setup initial stock level (Expected: 10)
    stock_level = StockLevel(
        item_id=base_item.id,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("10")
    )
    tenant_session.add(stock_level)

    # Fund 10 units in CostLayer
    movement = StockMovement(
        item_id=base_item.id,
        warehouse_id=main_warehouse.id,
        qty=Decimal("10"),
        movement_type="IN"
    )
    tenant_session.add(movement)
    await tenant_session.flush()

    layer = CostLayer(
        item_id=base_item.id,
        warehouse_id=main_warehouse.id,
        unit_cost_original=Decimal("10.00"),
        unit_cost_current=Decimal("10.00"),
        qty_received=Decimal("10"),
        qty_remaining=Decimal("10")
    )
    tenant_session.add(layer)
    await tenant_session.commit()

    # 2. Create Draft Stock Take
    st = StockTake(warehouse_id=main_warehouse.id, reference_id="ST-001")
    tenant_session.add(st)
    await tenant_session.commit()

    # 3. Start Count (should snapshot 10)
    await start_count(tenant_session, st.id)
    await tenant_session.commit()
    
    await tenant_session.refresh(st)
    assert st.status == StockTakeStatus.COUNTING

    # 4. Blind Count Sheet (should mask expected_qty)
    sheet = await get_blind_count_sheet(tenant_session, st.id)
    assert len(sheet) == 1
    assert sheet[0]["expected_qty"] is None

    # 5. Record Count (Counted: 8 -> Shrinkage of 2)
    line_id = sheet[0]["line_id"]
    counts = [
        {"line_id": line_id, "counted_qty": Decimal("8")}
    ]
    
    # Add a new unexpected item count (Gain)
    new_item = Item(sku="NEW-ST", name="New Item")
    tenant_session.add(new_item)
    await tenant_session.commit()

    counts.append({
        "item_id": new_item.id,
        "counted_qty": Decimal("5")
    })

    await record_count(tenant_session, st.id, counts)
    await tenant_session.commit()

    await tenant_session.refresh(st)
    assert st.status == StockTakeStatus.REVIEW

    # 6. Post Stock Take
    await post_stock_take(tenant_session, st.id)
    await tenant_session.commit()

    await tenant_session.refresh(st)
    assert st.status == StockTakeStatus.POSTED

    # 7. Verify Shrinkage applied (Quantity went from 10 to 8)
    await tenant_session.refresh(stock_level)
    assert stock_level.quantity == Decimal("8")

    # CostLayer should have 8 remaining
    await tenant_session.refresh(layer)
    assert layer.qty_remaining == Decimal("8")

    # 8. Verify Gain applied (New item has 5 units)
    stmt = select(StockLevel).where(StockLevel.item_id == new_item.id)
    new_level = (await tenant_session.execute(stmt)).scalar_one()
    assert new_level.quantity == Decimal("5")

    stmt_layer = select(CostLayer).where(CostLayer.item_id == new_item.id)
    new_layer = (await tenant_session.execute(stmt_layer)).scalar_one()
    assert new_layer.qty_remaining == Decimal("5")
    assert new_layer.unit_cost_current == Decimal("0") # Fallback to 0

    # 9. Verify Outbox event created
    stmt_event = select(OutboxEvent).where(OutboxEvent.event_type == "inventory.stock_take_posted")
    event = (await tenant_session.execute(stmt_event)).scalar_one_or_none()
    assert event is not None
    assert "total_loss_qty" in event.payload["payload"]
    assert event.payload["payload"]["total_loss_qty"] == "2.0000"
    assert event.payload["payload"]["total_gain_qty"] == "5.0000"
