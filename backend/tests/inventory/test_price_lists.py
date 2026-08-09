import pytest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.inventory.models.core import Item, ItemVariant
from app.modules.inventory.models.pricing import PriceList, PriceListRule

@pytest.mark.asyncio
async def test_price_list_and_rules(db_session: AsyncSession):
    item_id = uuid4()
    variant_id = uuid4()
    
    item = Item(id=item_id, name="Widget", sku="WIDGET-01")
    variant = ItemVariant(id=variant_id, item_id=item_id, name="Red Widget", sku="WIDGET-01-RED", price=Decimal("10.0"))
    
    pl = PriceList(name="Wholesale Pricing", currency="EGP")
    db_session.add(item)
    db_session.add(variant)
    db_session.add(pl)
    await db_session.flush()
    
    # Create rule with volume discount
    rule = PriceListRule(
        price_list_id=pl.id,
        item_id=item_id,
        variant_id=variant_id,
        min_qty=Decimal("100"),
        unit_price=Decimal("8.50")
    )
    db_session.add(rule)
    await db_session.commit()
    
    # Retrieve and verify
    stmt = select(PriceListRule).where(PriceListRule.price_list_id == pl.id)
    result = await db_session.execute(stmt)
    rules = result.scalars().all()
    
    assert len(rules) == 1
    assert rules[0].min_qty == Decimal("100")
    assert rules[0].unit_price == Decimal("8.50")
