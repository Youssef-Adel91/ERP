import pytest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models.core import Item, Warehouse, StockLevel
from app.modules.inventory.models.reorder import StockReorderRule
from app.modules.inventory.reports.reorder import get_needs_reordering_report

@pytest.mark.asyncio
async def test_get_needs_reordering_report(db_session: AsyncSession):
    # Setup test data
    warehouse_id = uuid4()
    warehouse = Warehouse(id=warehouse_id, name="Main Warehouse", code="MAIN-1")
    
    item_id = uuid4()
    item = Item(id=item_id, name="Test Item", sku="TEST-SKU", requires_batch=False, requires_serial=False)
    
    # Needs reordering: quantity (10) - reserved (2) = 8 <= 10 (reorder point)
    rule = StockReorderRule(
        item_id=item_id,
        warehouse_id=warehouse_id,
        reorder_point=Decimal("10"),
        reorder_qty=Decimal("50")
    )
    
    stock_level = StockLevel(
        item_id=item_id,
        warehouse_id=warehouse_id,
        quantity=Decimal("10"),
        qty_reserved=Decimal("2")
    )
    
    db_session.add(warehouse)
    db_session.add(item)
    db_session.add(rule)
    db_session.add(stock_level)
    await db_session.commit()
    
    report = await get_needs_reordering_report(db_session)
    
    assert len(report) == 1
    row = report[0]
    assert row["sku"] == "TEST-SKU"
    assert row["available_qty"] == 8.0
    assert row["suggested_reorder_qty"] == 50.0

@pytest.mark.asyncio
async def test_does_not_need_reordering(db_session: AsyncSession):
    warehouse_id = uuid4()
    warehouse = Warehouse(id=warehouse_id, name="Main Warehouse", code="MAIN-2")
    item_id = uuid4()
    item = Item(id=item_id, name="Test Item 2", sku="TEST-SKU-2")
    
    # Does NOT need reordering: quantity (20) - reserved (0) = 20 > 10
    rule = StockReorderRule(
        item_id=item_id,
        warehouse_id=warehouse_id,
        reorder_point=Decimal("10"),
        reorder_qty=Decimal("50")
    )
    
    stock_level = StockLevel(
        item_id=item_id,
        warehouse_id=warehouse_id,
        quantity=Decimal("20"),
        qty_reserved=Decimal("0")
    )
    
    db_session.add_all([warehouse, item, rule, stock_level])
    await db_session.commit()
    
    report = await get_needs_reordering_report(db_session)
    
    # We should only get the items that are below the reorder point
    # Since we use the same database, the previous test's item might be here,
    # but THIS test's item (TEST-SKU-2) should NOT be in the report.
    skus = [r["sku"] for r in report]
    assert "TEST-SKU-2" not in skus
