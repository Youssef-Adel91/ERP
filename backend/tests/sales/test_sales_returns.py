from decimal import Decimal
from uuid import uuid4

import pytest
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
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.sales.models.returns import SalesReturnStatus
from app.modules.sales.services.fulfillment import fulfill_sales_order
from app.modules.sales.services.invoicing import generate_invoice_from_order, post_invoice
from app.modules.sales.services.orders import confirm_sales_order, create_sales_order
from app.modules.sales.services.returns import (
    create_sales_return,
    post_credit_note,
    process_sales_return,
)
from app.modules.system.models import OutboxEvent


@pytest.fixture
def tenant_session(db_session: AsyncSession):
    return db_session


@pytest.fixture
async def sample_warehouse(tenant_session: AsyncSession) -> Warehouse:
    wh = Warehouse(code=f"WH-{uuid4().hex[:4].upper()}", name="Returns Test Warehouse")
    tenant_session.add(wh)
    await tenant_session.commit()
    await tenant_session.refresh(wh)
    return wh


@pytest.fixture
async def sample_contact_a(tenant_session: AsyncSession) -> Contact:
    contact = Contact(name="Customer Alpha", contact_type=ContactType.CUSTOMER)
    tenant_session.add(contact)
    await tenant_session.commit()
    await tenant_session.refresh(contact)
    return contact


@pytest.fixture
async def sample_contact_b(tenant_session: AsyncSession) -> Contact:
    contact = Contact(name="Customer Beta", contact_type=ContactType.CUSTOMER)
    tenant_session.add(contact)
    await tenant_session.commit()
    await tenant_session.refresh(contact)
    return contact


@pytest.fixture
async def sample_item_with_100_cogs(
    tenant_session: AsyncSession, sample_warehouse: Warehouse
) -> tuple[Item, UnitOfMeasure]:
    # Item starts with standard_cost of 50.0000
    item = Item(
        sku=f"RET-ITEM-{uuid4().hex[:6].upper()}",
        name="Exact COGS Reversal Item",
        standard_cost=Decimal("50.0000"),
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

    # Cost Layer received at exactly 100.0000 EGP
    layer = CostLayer(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        qty_received=Decimal("10"),
        qty_remaining=Decimal("10"),
        unit_cost_original=Decimal("100.0000"),
        unit_cost_current=Decimal("100.0000"),
        sequence_no=1,
    )
    tenant_session.add(layer)
    await tenant_session.commit()
    await tenant_session.refresh(item)
    await tenant_session.refresh(uom_piece)
    return item, uom_piece


@pytest.mark.asyncio
async def test_sales_return_exact_cost_reversal_and_credit_note(
    tenant_session: AsyncSession,
    sample_contact_a: Contact,
    sample_warehouse: Warehouse,
    sample_item_with_100_cogs: tuple[Item, UnitOfMeasure],
):
    item, uom = sample_item_with_100_cogs

    # 1. Create, confirm, and fulfill order for 4 units @ 150 EGP
    lines_data = [
        {
            "item_id": str(item.id),
            "uom_id": str(uom.id),
            "qty": "4",
            "unit_price": "150.0000",
            "tax_rate": "0.1400",
        }
    ]
    order = await create_sales_order(
        tenant_session, sample_contact_a.id, lines_data
    )
    await confirm_sales_order(tenant_session, order.id, sample_warehouse.id)
    await fulfill_sales_order(
        tenant_session,
        order.id,
        sample_warehouse.id,
        [{"item_id": str(item.id), "qty": "4", "uom_id": str(uom.id)}],
    )

    # 2. Invoice the order
    invoice = await generate_invoice_from_order(tenant_session, order.id)
    invoice = await post_invoice(tenant_session, invoice.id)
    assert invoice.status == SalesInvoiceStatus.POSTED
    assert len(invoice.lines) == 1

    # 3. Add a new CostLayer at 200.0000 EGP so current WAC/latest cost is 200.0000 EGP,
    # proving that the return uses exact historical COGS (100.0000 EGP) instead of current cost.
    new_layer = CostLayer(
        item_id=item.id,
        warehouse_id=sample_warehouse.id,
        qty_received=Decimal("10"),
        qty_remaining=Decimal("10"),
        unit_cost_original=Decimal("200.0000"),
        unit_cost_current=Decimal("200.0000"),
        sequence_no=2,
    )
    tenant_session.add(new_layer)
    await tenant_session.commit()

    # 4. Create Sales Return in DRAFT for 2 returned units
    return_line_data = [
        {
            "original_invoice_line_id": str(invoice.lines[0].id),
            "item_id": str(item.id),
            "uom_id": str(uom.id),
            "qty": "2",
            "unit_price": "150.0000",
            "tax_rate": "0.1400",
        }
    ]
    sales_return = await create_sales_return(
        session=tenant_session,
        invoice_id=invoice.id,
        contact_id=sample_contact_a.id,
        lines_data=return_line_data,
        order_id=order.id,
    )
    assert sales_return.status == SalesReturnStatus.DRAFT
    assert sales_return.subtotal == Decimal("300.0000")
    assert sales_return.tax_total == Decimal("42.0000")
    assert sales_return.grand_total == Decimal("342.0000")

    # 5. Process Sales Return -> verifies exact historical COGS reversal (Hook 2)
    processed_return = await process_sales_return(
        tenant_session, sales_return.id, sample_warehouse.id
    )
    assert processed_return.status == SalesReturnStatus.RECEIVED

    # Query newest CostLayer for item.id
    layers_stmt = (
        select(CostLayer)
        .where(CostLayer.item_id == item.id)
        .order_by(CostLayer.id.desc())
    )
    all_layers = (await tenant_session.execute(layers_stmt)).scalars().all()
    # Find the inbound layer created by the return (qty_received == 2)
    return_layer = next((lyr for lyr in all_layers if lyr.qty_received == Decimal("2")), None)
    assert return_layer is not None
    # Must equal exactly 100.0000 (historical COGS), not 200.0000 (current standard cost) or 50.0000 (initial standard cost)
    assert return_layer.unit_cost_original == Decimal("100.0000")
    assert return_layer.unit_cost_current == Decimal("100.0000")

    # 6. Post Credit Note -> verifies Credit Note creation & Outbox Event emission
    credited_return = await post_credit_note(tenant_session, processed_return.id)
    assert credited_return.status == SalesReturnStatus.CREDITED
    assert credited_return.credit_note_id is not None

    credit_note = await tenant_session.get(SalesInvoice, credited_return.credit_note_id)
    assert credit_note is not None
    assert credit_note.status == SalesInvoiceStatus.POSTED
    assert credit_note.subtotal == Decimal("-300.0000")
    assert credit_note.tax_total == Decimal("-42.0000")
    assert credit_note.grand_total == Decimal("-342.0000")

    # Verify OutboxEvent for credit note
    event_stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.event_type == "sales.credit_note_posted")
        .order_by(OutboxEvent.created_at.desc())
    )
    outbox_event = (await tenant_session.execute(event_stmt)).scalars().first()
    assert outbox_event is not None
    payload = outbox_event.payload["payload"]
    assert payload["return_id"] == str(credited_return.id)
    assert payload["credit_note_id"] == str(credit_note.id)
    assert payload["subtotal"] == "-300.0000"
    assert payload["tax_total"] == "-42.0000"
    assert payload["grand_total"] == "-342.0000"
    assert len(payload["lines"]) == 1
    assert payload["lines"][0]["line_total"] == "-300.0000"


@pytest.mark.asyncio
async def test_sales_return_fraud_prevention_hook(
    tenant_session: AsyncSession,
    sample_contact_a: Contact,
    sample_contact_b: Contact,
    sample_warehouse: Warehouse,
):
    """
    1. Create a serialized item sold to Customer Alpha.
    2. Attempt to return the item by Customer Beta -> Must fail with Return fraud detected.
    3. Return the item by Customer Alpha -> Must succeed and transition serial state to RETURNED.
    """
    item = Item(
        sku=f"RET-SER-{uuid4().hex[:6].upper()}",
        name="Serialized Return Item",
        requires_serial=True,
        standard_cost=Decimal("120.0000"),
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
        serial_no=f"SN-RET-{uuid4().hex[:6].upper()}",
        state=SerialState.IN_STOCK,
        warehouse_id=sample_warehouse.id,
    )
    tenant_session.add(serial)
    await tenant_session.flush()

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
        qty_received=Decimal("1"),
        qty_remaining=Decimal("1"),
        unit_cost_original=Decimal("120.0000"),
        unit_cost_current=Decimal("120.0000"),
        sequence_no=1,
    )
    tenant_session.add(layer)
    await tenant_session.commit()

    # Sell to Customer Alpha
    lines_data = [
        {
            "item_id": str(item.id),
            "uom_id": str(uom_piece.id),
            "qty": "1",
            "unit_price": "250.0000",
        }
    ]
    order = await create_sales_order(
        tenant_session, sample_contact_a.id, lines_data
    )
    await confirm_sales_order(tenant_session, order.id, sample_warehouse.id)
    await fulfill_sales_order(
        tenant_session,
        order.id,
        sample_warehouse.id,
        [
            {
                "item_id": str(item.id),
                "qty": "1",
                "uom_id": str(uom_piece.id),
                "serial_id": str(serial.id),
            }
        ],
    )
    invoice = await generate_invoice_from_order(tenant_session, order.id)
    invoice = await post_invoice(tenant_session, invoice.id)

    # Attempt fraudulent return by Customer Beta
    return_line_beta = [
        {
            "original_invoice_line_id": str(invoice.lines[0].id),
            "item_id": str(item.id),
            "uom_id": str(uom_piece.id),
            "qty": "1",
            "unit_price": "250.0000",
            "serial_id": str(serial.id),
        }
    ]
    fraud_return = await create_sales_return(
        session=tenant_session,
        invoice_id=invoice.id,
        contact_id=sample_contact_b.id,
        lines_data=return_line_beta,
        order_id=order.id,
    )

    with pytest.raises(ValueError, match="Return fraud detected"):
        await process_sales_return(
            tenant_session, fraud_return.id, sample_warehouse.id
        )

    # Valid return by Customer Alpha
    return_line_alpha = [
        {
            "original_invoice_line_id": str(invoice.lines[0].id),
            "item_id": str(item.id),
            "uom_id": str(uom_piece.id),
            "qty": "1",
            "unit_price": "250.0000",
            "serial_id": str(serial.id),
        }
    ]
    valid_return = await create_sales_return(
        session=tenant_session,
        invoice_id=invoice.id,
        contact_id=sample_contact_a.id,
        lines_data=return_line_alpha,
        order_id=order.id,
    )
    processed_alpha_return = await process_sales_return(
        tenant_session, valid_return.id, sample_warehouse.id
    )
    assert processed_alpha_return.status == SalesReturnStatus.RECEIVED

    await tenant_session.refresh(serial)
    assert serial.state == SerialState.RETURNED
