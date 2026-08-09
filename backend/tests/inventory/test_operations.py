import pytest
from uuid import uuid4
from decimal import Decimal

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models.core import (
    Item,
    StockLevel,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.inventory.services.reservation import (
    reserve_stock,
    release_reservation,
)
from app.modules.inventory.exceptions import InsufficientStockError
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
async def base_item(tenant_session: AsyncSession):
    item = Item(sku="BOTTLE-001", name="Bottle of Water")
    tenant_session.add(item)
    
    uom_base = UnitOfMeasure(item_id=item.id, name="Piece", conversion_factor=Decimal("1.0"), is_base=True)
    tenant_session.add(uom_base)
    
    uom_carton = UnitOfMeasure(item_id=item.id, name="Carton", conversion_factor=Decimal("12.0"), is_base=False)
    tenant_session.add(uom_carton)
    
    await tenant_session.commit()
    return item, uom_carton


@pytest.mark.asyncio
async def test_uom_translation(tenant_session: AsyncSession, base_item: tuple[Item, UnitOfMeasure], main_warehouse: Warehouse):
    item, uom_carton = base_item
    
    # Give the warehouse 30 pieces
    stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("30")
    )
    tenant_session.add(stock_level)
    await tenant_session.commit()
    
    # Consume 2 Cartons (2 * 12 = 24 Pieces)
    req = CostingRequest(
        item_id=item.id,
        variant_id=None,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("2"),
        movement_type="OUT",
        uom_id=uom_carton.id
    )
    await consume_stock(tenant_session, [req])
    await tenant_session.commit()
    await tenant_session.refresh(stock_level)
    
    # 30 - 24 = 6 Pieces remaining
    assert stock_level.quantity == Decimal("6")


@pytest.mark.asyncio
async def test_stock_reservation(tenant_session: AsyncSession, base_item: tuple[Item, UnitOfMeasure], main_warehouse: Warehouse):
    item, _ = base_item
    
    # Give the warehouse 10 pieces
    stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=main_warehouse.id,
        quantity=Decimal("10"),
        qty_reserved=Decimal("0")
    )
    tenant_session.add(stock_level)
    await tenant_session.commit()
    
    # Reserve 6 pieces
    success = await reserve_stock(
        session=tenant_session,
        item_id=item.id,
        warehouse_id=main_warehouse.id,
        qty=Decimal("6")
    )
    assert success is True
    await tenant_session.commit()
    await tenant_session.refresh(stock_level)
    
    assert stock_level.qty_reserved == Decimal("6")
    
    # Try to reserve 5 more pieces (only 4 available)
    with pytest.raises(InsufficientStockError):
        await reserve_stock(
            session=tenant_session,
            item_id=item.id,
            warehouse_id=main_warehouse.id,
            qty=Decimal("5")
        )
    
    # Release 2 pieces
    await release_reservation(
        session=tenant_session,
        item_id=item.id,
        warehouse_id=main_warehouse.id,
        qty=Decimal("2")
    )
    await tenant_session.commit()
    await tenant_session.refresh(stock_level)
    
    assert stock_level.qty_reserved == Decimal("4")
