from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.contacts.models import Contact, ContactType
from app.modules.inventory.models.core import (
    CostLayer,
    Item,
    StockLevel,
    StockMovement,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.sales.models.core import SalesOrderStatus
from app.modules.sales.models.invoice import SalesInvoiceStatus
from app.modules.sales.services.fulfillment import fulfill_sales_order
from app.modules.sales.services.invoicing import generate_invoice_from_order, post_invoice
from app.modules.sales.services.orders import confirm_sales_order, create_sales_order
from app.modules.system.models import OutboxEvent


@pytest.fixture
def tenant_session(db_session: AsyncSession):
    return db_session


@pytest.fixture
async def sample_contact(tenant_session: AsyncSession) -> Contact:
    contact = Contact(
        name="Acme Invoicing Customer",
        contact_type=ContactType.CUSTOMER,
    )
    tenant_session.add(contact)
    await tenant_session.commit()
    await tenant_session.refresh(contact)
    return contact


@pytest.fixture
async def sample_warehouse(tenant_session: AsyncSession) -> Warehouse:
    wh = Warehouse(name="Invoicing WH", code=f"INV-{uuid4().hex[:4].upper()}")
    tenant_session.add(wh)
    await tenant_session.commit()
    await tenant_session.refresh(wh)
    return wh


@pytest.fixture
async def sample_item_with_stock(
    tenant_session: AsyncSession, sample_warehouse: Warehouse
) -> tuple[Item, UnitOfMeasure]:
    item = Item(sku=f"INV-{uuid4().hex[:6].upper()}", name="Invoicable Item")
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

    stock_level = StockLevel(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("20"),
        qty_reserved=Decimal("0"),
    )
    tenant_session.add(stock_level)

    in_mvt = StockMovement(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        qty=Decimal("20"),
        movement_type="IN",
    )
    tenant_session.add(in_mvt)
    await tenant_session.flush()

    layer = CostLayer(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        qty_received=Decimal("20"),
        qty_remaining=Decimal("20"),
        unit_cost_original=Decimal("50.0000"),
        unit_cost_current=Decimal("50.0000"),
        sequence_no=1,
    )
    tenant_session.add(layer)
    await tenant_session.commit()
    await tenant_session.refresh(item)
    await tenant_session.refresh(uom_piece)
    return item, uom_piece


@pytest.mark.asyncio
async def test_full_invoicing_cycle_and_outbox_event(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_warehouse: Warehouse,
    sample_item_with_stock: tuple[Item, UnitOfMeasure],
):
    """
    1. Create and confirm a sales order for 4 units @ 150.00.
    2. Fulfill the order.
    3. Generate invoice from order -> verify DRAFT status and totals (14% tax).
    4. Post invoice -> verify POSTED status, SalesOrder INVOICED status, and Outbox event.
    """
    item, uom = sample_item_with_stock

    # 1. Create order
    lines_data = [
        {
            "item_id": item.id,
            "uom_id": uom.id,
            "qty": Decimal("4.0000"),
            "unit_price": Decimal("150.0000"),
        }
    ]
    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        order_number=f"SO-INV-{uuid4().hex[:4].upper()}",
        lines_data=lines_data,
    )
    assert order.status == SalesOrderStatus.DRAFT

    # 2. Confirm order
    await confirm_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
    )
    assert order.status == SalesOrderStatus.CONFIRMED

    # 3. Fulfill order
    fulfillment_lines = [
        {
            "line_id": order.lines[0].id,
            "qty": Decimal("4.0000"),
        }
    ]
    res = await fulfill_sales_order(
        session=tenant_session,
        order_id=order.id,
        warehouse_id=sample_warehouse.id,
        fulfillment_lines=fulfillment_lines,
    )
    assert res.order.status == SalesOrderStatus.FULFILLED

    # 4. Generate invoice
    invoice = await generate_invoice_from_order(
        session=tenant_session,
        order_id=order.id,
        default_tax_rate=Decimal("0.1400"),
    )
    assert invoice.status == SalesInvoiceStatus.DRAFT
    assert invoice.order_id == order.id
    assert invoice.contact_id == sample_contact.id
    assert len(invoice.lines) == 1

    # Subtotal = 4 * 150.00 = 600.00
    # Tax (14%) = 84.00
    # Grand Total = 684.00
    assert invoice.subtotal == Decimal("600.0000")
    assert invoice.tax_total == Decimal("84.0000")
    assert invoice.grand_total == Decimal("684.0000")

    # 5. Post invoice
    posted_invoice = await post_invoice(
        session=tenant_session,
        invoice_id=invoice.id,
    )
    assert posted_invoice.status == SalesInvoiceStatus.POSTED
    assert order.status == SalesOrderStatus.INVOICED

    # 6. Verify Outbox event
    stmt_event = select(OutboxEvent).where(OutboxEvent.event_type == "sales.invoice_posted")
    events = (await tenant_session.execute(stmt_event)).scalars().all()
    assert len(events) >= 1

    # Find our specific event
    event = next((e for e in events if e.payload["payload"]["invoice_id"] == str(invoice.id)), None)
    assert event is not None
    assert event.payload["payload"]["order_id"] == str(order.id)
    assert event.payload["payload"]["contact_id"] == str(sample_contact.id)
    assert event.payload["payload"]["subtotal"] == "600.0000"
    assert event.payload["payload"]["tax_total"] == "84.0000"
    assert event.payload["payload"]["grand_total"] == "684.0000"
    assert len(event.payload["payload"]["lines"]) == 1
    assert event.payload["payload"]["lines"][0]["item_id"] == str(item.id)
    assert event.payload["payload"]["lines"][0]["qty"] == "4.0000"
    assert event.payload["payload"]["lines"][0]["line_total"] == "600.0000"
    assert event.payload["payload"]["lines"][0]["tax_amount"] == "84.0000"


@pytest.mark.asyncio
async def test_generate_invoice_fails_on_unfulfilled_order(
    tenant_session: AsyncSession,
    sample_contact: Contact,
    sample_warehouse: Warehouse,
    sample_item_with_stock: tuple[Item, UnitOfMeasure],
):
    """
    Attempting to generate an invoice for a DRAFT or CONFIRMED order without fulfilled qty should fail.
    """
    item, uom = sample_item_with_stock
    order = await create_sales_order(
        session=tenant_session,
        contact_id=sample_contact.id,
        order_number=f"SO-FAIL-{uuid4().hex[:4].upper()}",
        lines_data=[
            {
                "item_id": item.id,
                "uom_id": uom.id,
                "qty": Decimal("2.0000"),
                "unit_price": Decimal("100.0000"),
            }
        ],
    )
    with pytest.raises(ValueError, match="Cannot generate invoice for sales order in status"):
        await generate_invoice_from_order(tenant_session, order.id)
