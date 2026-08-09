from decimal import Decimal
import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.contacts.models import Contact, ContactType
from app.modules.inventory.exceptions import InsufficientStockError
from app.modules.inventory.models.core import Item, StockLevel, UnitOfMeasure, Warehouse
from app.modules.inventory.models.pricing import PriceList, PriceListRule
from app.modules.sales.models.core import SalesOrderStatus
from app.modules.sales.services.orders import confirm_sales_order, create_sales_order


@pytest.fixture
def tenant_session(db_session: AsyncSession):
    return db_session


@pytest.fixture
async def sample_contact(tenant_session: AsyncSession) -> Contact:
    contact = Contact(
        name="Test Customer LLC",
        contact_type=ContactType.CUSTOMER,
    )
    tenant_session.add(contact)
    await tenant_session.commit()
    await tenant_session.refresh(contact)
    return contact


@pytest.fixture
async def sample_item_with_uoms(tenant_session: AsyncSession) -> tuple[Item, UnitOfMeasure, UnitOfMeasure]:
    item = Item(sku=f"SKU-{uuid4().hex[:6].upper()}", name="Test Beverage")
    tenant_session.add(item)
    await tenant_session.flush()

    uom_piece = UnitOfMeasure(
        item_id=item.id,
        name="Piece",
        conversion_factor=Decimal("1.0"),
        is_base=True,
    )
    uom_carton = UnitOfMeasure(
        item_id=item.id,
        name="Carton",
        conversion_factor=Decimal("12.0"),
        is_base=False,
    )
    tenant_session.add(uom_piece)
    tenant_session.add(uom_carton)
    await tenant_session.commit()
    return item, uom_piece, uom_carton


@pytest.fixture
async def sample_warehouse(tenant_session: AsyncSession) -> Warehouse:
    wh = Warehouse(name="Main Sales WH", code=f"MAIN-{uuid4().hex[:4].upper()}")
    tenant_session.add(wh)
    await tenant_session.commit()
    await tenant_session.refresh(wh)
    return wh


@pytest.mark.asyncio
async def test_create_sales_order_with_pricing_hook(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_item_with_uoms: tuple[Item, UnitOfMeasure, UnitOfMeasure],
):
    item, uom_piece, _ = sample_item_with_uoms

    price_list = PriceList(name="Wholesale Price List", currency="EGP")
    tenant_session.add(price_list)
    await tenant_session.flush()

    # Rule 1: >= 1 unit -> 50.0 EGP
    rule1 = PriceListRule(
        price_list_id=price_list.id,
        item_id=item.id,
        min_qty=Decimal("1.0"),
        unit_price=Decimal("50.0"),
    )
    # Rule 2 (Volume break): >= 10 units -> 45.0 EGP
    rule2 = PriceListRule(
        price_list_id=price_list.id,
        item_id=item.id,
        min_qty=Decimal("10.0"),
        unit_price=Decimal("45.0"),
    )
    tenant_session.add(rule1)
    tenant_session.add(rule2)
    await tenant_session.commit()

    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        price_list_id=price_list.id,
        lines_data=[
            {"item_id": item.id, "qty": Decimal("15.0"), "uom_id": uom_piece.id}
        ],
    )
    await tenant_session.commit()

    assert order.status == SalesOrderStatus.DRAFT
    assert len(order.lines) == 1
    # Should select the 45.0 volume break
    assert order.lines[0].unit_price == Decimal("45.0")
    assert order.lines[0].line_total == Decimal("675.0000")
    assert order.total_amount == Decimal("675.0000")


@pytest.mark.asyncio
async def test_confirm_sales_order_reserves_stock_with_uom(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_item_with_uoms: tuple[Item, UnitOfMeasure, UnitOfMeasure],
    sample_warehouse: Warehouse,
):
    item, _, uom_carton = sample_item_with_uoms

    # 100 Pieces on hand, 0 reserved
    stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("100.0"),
        qty_reserved=Decimal("0.0"),
    )
    tenant_session.add(stock_level)
    await tenant_session.commit()

    # Create SO for 2 Cartons (2 * 12 = 24 Pieces)
    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        lines_data=[
            {
                "item_id": item.id,
                "qty": Decimal("2.0"),
                "uom_id": uom_carton.id,
                "unit_price": Decimal("120.0"),
            }
        ],
    )
    await tenant_session.commit()

    confirmed_order = await confirm_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
    )
    await tenant_session.commit()

    assert confirmed_order.status == SalesOrderStatus.CONFIRMED

    await tenant_session.refresh(stock_level)
    # Check that 24 pieces were reserved (2 cartons * 12 cf)
    assert stock_level.qty_reserved == Decimal("24.0000")


@pytest.mark.asyncio
async def test_confirm_sales_order_insufficient_stock_aborts(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_item_with_uoms: tuple[Item, UnitOfMeasure, UnitOfMeasure],
    sample_warehouse: Warehouse,
):
    item, uom_piece, _ = sample_item_with_uoms

    # Only 10 pieces available
    stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("10.0"),
        qty_reserved=Decimal("0.0"),
    )
    tenant_session.add(stock_level)
    await tenant_session.commit()

    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        lines_data=[
            {
                "item_id": item.id,
                "qty": Decimal("20.0"),
                "uom_id": uom_piece.id,
                "unit_price": Decimal("10.0"),
            }
        ],
    )
    await tenant_session.commit()

    with pytest.raises(InsufficientStockError):
        await confirm_sales_order(
            session=tenant_session,
            order_id=order.id,
            warehouse_id=sample_warehouse.id,
        )

    await tenant_session.refresh(order)
    await tenant_session.refresh(stock_level)

    assert order.status == SalesOrderStatus.DRAFT
    assert stock_level.qty_reserved == Decimal("0.0")
