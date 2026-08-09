import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.inventory.models import (
    CostLayer,
    Item,
    StockLevel,
    StockTransfer,
    StockTransferLine,
    TransferStatus,
    Warehouse,
    WarehouseType,
)
from app.modules.inventory.services.transfer import (
    ReceiptLine,
    dispatch_transfer,
    receive_transfer,
)

@pytest.fixture
def tenant_session(db_session):
    return db_session

@pytest.fixture
async def main_warehouse(tenant_session):
    warehouse = Warehouse(name="Main", code="MAIN01", type=WarehouseType.MAIN)
    tenant_session.add(warehouse)
    await tenant_session.commit()
    return warehouse

@pytest.fixture
async def retail_warehouse(tenant_session):
    warehouse = Warehouse(name="Retail", code="RET01", type=WarehouseType.RETAIL)
    tenant_session.add(warehouse)
    await tenant_session.commit()
    return warehouse

@pytest.fixture
async def transit_warehouse(tenant_session):
    warehouse = Warehouse(name="Transit", code="TRN01", type=WarehouseType.TRANSIT)
    tenant_session.add(warehouse)
    await tenant_session.commit()
    return warehouse

@pytest.fixture
async def test_item(tenant_session):
    item = Item(sku="ITEM-001", name="Transfer Item")
    tenant_session.add(item)
    await tenant_session.commit()
    return item


@pytest.mark.asyncio
async def test_transfer_lifecycle_and_shrinkage(
    tenant_session: AsyncSession,
    main_warehouse: Warehouse,
    transit_warehouse: Warehouse,
    retail_warehouse: Warehouse,
    test_item: Item,
):
    # 1. Setup Initial Stock in Source Warehouse
    source_layer = CostLayer(
        item_id=test_item.id,
        warehouse_id=main_warehouse.id,
        qty_received=Decimal("100"),
        qty_remaining=Decimal("100"),
        unit_cost_original=Decimal("15.50"),
        unit_cost_current=Decimal("15.50"),
    )
    tenant_session.add(source_layer)
    
    source_level = StockLevel(
        item_id=test_item.id,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("100")
    )
    tenant_session.add(source_level)
    await tenant_session.flush()

    # 2. Create Transfer Draft
    transfer = StockTransfer(
        transfer_number="TRN-001",
        source_warehouse_id=main_warehouse.id,
        destination_warehouse_id=retail_warehouse.id,
        transit_warehouse_id=transit_warehouse.id,
        status=TransferStatus.DRAFT
    )
    tenant_session.add(transfer)
    await tenant_session.flush()

    line = StockTransferLine(
        transfer_id=transfer.id,
        item_id=test_item.id,
        qty_dispatched=Decimal("40"),
    )
    tenant_session.add(line)
    await tenant_session.commit()

    # 3. Dispatch Transfer
    await dispatch_transfer(tenant_session, transfer.id)
    await tenant_session.commit()
    await tenant_session.refresh(transfer)
    await tenant_session.refresh(line)

    assert transfer.status == TransferStatus.IN_TRANSIT
    assert transfer.dispatched_at is not None

    # Verify Source Warehouse StockLevel
    source_stock = (await tenant_session.execute(
        select(StockLevel).where(StockLevel.warehouse_id == main_warehouse.id)
    )).scalar_one()
    assert source_stock.quantity == Decimal("60")

    # Verify Transit Warehouse CostLayer and StockLevel
    transit_stock = (await tenant_session.execute(
        select(StockLevel).where(StockLevel.warehouse_id == transit_warehouse.id)
    )).scalar_one()
    assert transit_stock.quantity == Decimal("40")

    transit_layers = (await tenant_session.execute(
        select(CostLayer).where(CostLayer.warehouse_id == transit_warehouse.id)
    )).scalars().all()
    assert len(transit_layers) == 1
    assert transit_layers[0].qty_received == Decimal("40")
    assert transit_layers[0].unit_cost_current == Decimal("15.50")

    # 4. Receive Transfer (with shrinkage)
    # We dispatch 40, but only receive 38
    receipts = [ReceiptLine(line_id=line.id, qty_received=Decimal("38"))]
    await receive_transfer(tenant_session, transfer.id, receipts)
    await tenant_session.commit()
    await tenant_session.refresh(transfer)
    await tenant_session.refresh(line)

    assert transfer.status == TransferStatus.PARTIALLY_RECEIVED
    assert transfer.received_at is not None
    assert line.qty_received == Decimal("38")

    # Verify Transit Warehouse StockLevel (Shrinkage remains)
    transit_stock = (await tenant_session.execute(
        select(StockLevel).where(StockLevel.warehouse_id == transit_warehouse.id)
    )).scalar_one()
    assert transit_stock.quantity == Decimal("2")

    transit_layer = (await tenant_session.execute(
        select(CostLayer).where(CostLayer.warehouse_id == transit_warehouse.id)
    )).scalar_one()
    assert transit_layer.qty_remaining == Decimal("2")

    # Verify Destination Warehouse CostLayer and StockLevel
    dest_stock = (await tenant_session.execute(
        select(StockLevel).where(StockLevel.warehouse_id == retail_warehouse.id)
    )).scalar_one()
    assert dest_stock.quantity == Decimal("38")

    dest_layers = (await tenant_session.execute(
        select(CostLayer).where(CostLayer.warehouse_id == retail_warehouse.id)
    )).scalars().all()
    assert len(dest_layers) == 1
    assert dest_layers[0].qty_received == Decimal("38")
    assert dest_layers[0].qty_remaining == Decimal("38")
    assert dest_layers[0].unit_cost_current == Decimal("15.50")
