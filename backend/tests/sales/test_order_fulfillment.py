from decimal import Decimal
import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.contacts.models import Contact, ContactType
from app.modules.inventory.models.core import (
    CostLayer,
    Item,
    SerialNumber,
    SerialState,
    StockLevel,
    StockMovement,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.sales.models.core import SalesOrderStatus
from app.modules.sales.services.fulfillment import fulfill_sales_order
from app.modules.sales.services.orders import confirm_sales_order, create_sales_order


@pytest.fixture
def tenant_session(db_session: AsyncSession):
    return db_session


@pytest.fixture
async def sample_contact(tenant_session: AsyncSession) -> Contact:
    contact = Contact(
        name="Acme Fulfillment Corp",
        contact_type=ContactType.CUSTOMER,
    )
    tenant_session.add(contact)
    await tenant_session.commit()
    await tenant_session.refresh(contact)
    return contact


@pytest.fixture
async def sample_warehouse(tenant_session: AsyncSession) -> Warehouse:
    wh = Warehouse(name="Fulfillment WH", code=f"FUL-{uuid4().hex[:4].upper()}")
    tenant_session.add(wh)
    await tenant_session.commit()
    await tenant_session.refresh(wh)
    return wh


@pytest.fixture
async def sample_item_with_stock(
    tenant_session: AsyncSession, sample_warehouse: Warehouse
) -> tuple[Item, UnitOfMeasure]:
    item = Item(sku=f"FUL-{uuid4().hex[:6].upper()}", name="Test Gadget")
    tenant_session.add(item)
    await tenant_session.flush()

    uom_piece = UnitOfMeasure(
        item_id=item.id,
        name="Piece",
        conversion_factor=Decimal("1.0"),
        is_base=True,
    )
    tenant_session.add(uom_piece)
    await tenant_session.flush()

    # Add 10 units of initial stock and cost layer
    stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("10"),
        qty_reserved=Decimal("0"),
    )
    tenant_session.add(stock_level)

    in_mvt = StockMovement(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        qty=Decimal("10"),
        movement_type="IN",
    )
    tenant_session.add(in_mvt)
    await tenant_session.flush()

    layer = CostLayer(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        unit_cost_original=Decimal("100.00"),
        unit_cost_current=Decimal("100.00"),
        qty_received=Decimal("10"),
        qty_remaining=Decimal("10"),
    )
    tenant_session.add(layer)
    await tenant_session.commit()

    return item, uom_piece


@pytest.mark.asyncio
async def test_full_order_fulfillment_cycle(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_warehouse: Warehouse,
    sample_item_with_stock: tuple[Item, UnitOfMeasure],
):
    item, uom = sample_item_with_stock

    # 1. Create Sales Order for 5 units @ 150.00 EGP selling price
    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        order_number=f"SO-{uuid4().hex[:6].upper()}",
        lines_data=[
            {
                "item_id": item.id,
                "qty": Decimal("5"),
                "unit_price": Decimal("150.00"),
                "uom_id": uom.id,
            }
        ],
    )
    assert order.status == SalesOrderStatus.DRAFT

    # 2. Confirm Order (Reserves Stock)
    await confirm_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
    )
    assert order.status == SalesOrderStatus.CONFIRMED

    stock_level = (
        await tenant_session.execute(
            select(StockLevel).where(StockLevel.item_id == item.id)
        )
    ).scalar_one()
    assert stock_level.qty_reserved == Decimal("5")
    assert stock_level.quantity == Decimal("10")

    # 3. Fulfill Order (Releases Reservation, Consumes Stock, Creates SALES_ISSUE)
    res = await fulfill_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
        fulfillment_lines=[
            {
                "line_id": order.lines[0].id,
                "qty": Decimal("5"),
            }
        ],
    )
    await tenant_session.commit()

    assert res.order.status == SalesOrderStatus.FULFILLED
    assert res.order.lines[0].fulfilled_qty == Decimal("5")

    # Verify StockLevel is decremented and reservation is released
    await tenant_session.refresh(stock_level)
    assert stock_level.quantity == Decimal("5")
    assert stock_level.qty_reserved == Decimal("0")

    # Verify StockMovement with strict SALES_ISSUE type
    assert len(res.movements) == 1
    mvt = res.movements[0]
    assert mvt.movement_type == "SALES_ISSUE"
    assert mvt.qty == Decimal("-5")

    # Verify CostConsumption for COGS (5 * 100.00 = 500.00)
    assert len(res.consumptions) == 1
    consumption = res.consumptions[0]
    assert consumption.qty_consumed == Decimal("5")
    assert consumption.unit_cost_at_consumption == Decimal("100.00")
    assert (consumption.qty_consumed * consumption.unit_cost_at_consumption) == Decimal("500.00")


@pytest.mark.asyncio
async def test_partial_fulfillment_progression(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_warehouse: Warehouse,
    sample_item_with_stock: tuple[Item, UnitOfMeasure],
):
    item, uom = sample_item_with_stock

    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        order_number=f"SO-PARTIAL-{uuid4().hex[:6].upper()}",
        lines_data=[
            {
                "item_id": item.id,
                "qty": Decimal("8"),
                "unit_price": Decimal("150.00"),
                "uom_id": uom.id,
            }
        ],
    )
    await confirm_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
    )

    # 1. Partial fulfillment of 3 units
    res1 = await fulfill_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
        fulfillment_lines=[
            {
                "line_id": order.lines[0].id,
                "qty": Decimal("3"),
            }
        ],
    )
    await tenant_session.commit()

    assert res1.order.status == SalesOrderStatus.PARTIALLY_FULFILLED
    assert res1.order.lines[0].fulfilled_qty == Decimal("3")

    stock_level = (
        await tenant_session.execute(
            select(StockLevel).where(StockLevel.item_id == item.id)
        )
    ).scalar_one()
    assert stock_level.quantity == Decimal("7")
    assert stock_level.qty_reserved == Decimal("5")

    # 2. Fulfill remaining 5 units
    res2 = await fulfill_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
        fulfillment_lines=[
            {
                "line_id": order.lines[0].id,
                "qty": Decimal("5"),
            }
        ],
    )
    await tenant_session.commit()

    assert res2.order.status == SalesOrderStatus.FULFILLED
    assert res2.order.lines[0].fulfilled_qty == Decimal("8")
    await tenant_session.refresh(stock_level)
    assert stock_level.quantity == Decimal("2")
    assert stock_level.qty_reserved == Decimal("0")


@pytest.mark.asyncio
async def test_serialized_item_fulfillment_traceability(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_warehouse: Warehouse,
):
    # Setup serialized item
    item = Item(
        sku=f"SER-{uuid4().hex[:6].upper()}",
        name="Serialized Laptop",
        requires_serial=True,
    )
    tenant_session.add(item)
    await tenant_session.flush()

    uom_piece = UnitOfMeasure(
        item_id=item.id,
        name="Piece",
        conversion_factor=Decimal("1.0"),
        is_base=True,
    )
    tenant_session.add(uom_piece)
    await tenant_session.flush()

    serial = SerialNumber(
        item_id=item.id,
        serial_no=f"SN-{uuid4().hex[:8].upper()}",
        state=SerialState.IN_STOCK,
        warehouse_id=sample_warehouse.id,
    )
    tenant_session.add(serial)
    await tenant_session.flush()

    # General StockLevel for reservation and serial StockLevel for consumption
    general_stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        serial_id=None,
        quantity=Decimal("1"),
        qty_reserved=Decimal("0"),
    )
    serial_stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        serial_id=serial.id,
        quantity=Decimal("1"),
        qty_reserved=Decimal("0"),
    )
    tenant_session.add(general_stock_level)
    tenant_session.add(serial_stock_level)

    in_mvt = StockMovement(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        serial_id=serial.id,
        qty=Decimal("1"),
        movement_type="IN",
    )
    tenant_session.add(in_mvt)
    await tenant_session.flush()

    layer = CostLayer(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        serial_id=serial.id,
        unit_cost_original=Decimal("5000.00"),
        unit_cost_current=Decimal("5000.00"),
        qty_received=Decimal("1"),
        qty_remaining=Decimal("1"),
    )
    tenant_session.add(layer)
    await tenant_session.commit()

    # 1. Create and confirm sales order for 1 serialized unit
    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        order_number=f"SO-SER-{uuid4().hex[:6].upper()}",
        lines_data=[
            {
                "item_id": item.id,
                "qty": Decimal("1"),
                "unit_price": Decimal("7500.00"),
                "uom_id": uom_piece.id,
            }
        ],
    )
    await confirm_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
    )

    # 2. Fulfill passing specific serial_id
    res = await fulfill_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
        fulfillment_lines=[
            {
                "line_id": order.lines[0].id,
                "qty": Decimal("1"),
                "serial_id": serial.id,
            }
        ],
    )
    await tenant_session.commit()

    # Verify serial state progressed to SOLD and owner contact is bound
    await tenant_session.refresh(serial)
    assert serial.state == SerialState.SOLD
    assert serial.current_owner_contact_id == sample_contact.id

    # Verify SALES_ISSUE movement has serial_id
    assert len(res.movements) == 1
    assert res.movements[0].serial_id == serial.id
    assert res.movements[0].movement_type == "SALES_ISSUE"
