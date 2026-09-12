from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.sales.models.core import SalesOrder, SalesOrderStatus
from app.modules.sales.models.invoice import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesInvoiceStatus,
)


async def generate_invoice_from_order(
    session: AsyncSession,
    order_id: UUID,
    invoice_number: str | None = None,
    due_date: date | None = None,
    default_tax_rate: Decimal = Decimal("0.1400"),
) -> SalesInvoice:
    """
    Validates the order is FULFILLED or PARTIALLY_FULFILLED and generates
    a DRAFT SalesInvoice containing lines for fulfilled quantities.
    """
    stmt = (
        select(SalesOrder)
        .where(SalesOrder.id == order_id)
        .options(selectinload(SalesOrder.lines))
    )
    res = await session.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise ValueError(f"SalesOrder not found: {order_id}")

    if order.status not in (SalesOrderStatus.FULFILLED, SalesOrderStatus.PARTIALLY_FULFILLED):
        raise ValueError(
            f"Cannot generate invoice for sales order in status {order.status}. "
            "Order must be FULFILLED or PARTIALLY_FULFILLED."
        )

    fulfilled_lines = [line for line in order.lines if line.fulfilled_qty > Decimal("0.0000")]
    if not fulfilled_lines:
        raise ValueError(f"No fulfilled lines to invoice in sales order {order_id}")

    invoice_lines: list[SalesInvoiceLine] = []
    subtotal = Decimal("0.0000")
    tax_total = Decimal("0.0000")

    for line in fulfilled_lines:
        qty = line.fulfilled_qty
        unit_price = line.unit_price
        line_total = (qty * unit_price).quantize(Decimal("0.0001"))
        tax_amount = (line_total * default_tax_rate).quantize(Decimal("0.0001"))

        invoice_line = SalesInvoiceLine(
            item_id=line.item_id,
            variant_id=line.variant_id,
            uom_id=line.uom_id,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
            tax_rate=default_tax_rate,
            tax_amount=tax_amount,
        )
        invoice_lines.append(invoice_line)
        subtotal += line_total
        tax_total += tax_amount

    grand_total = subtotal + tax_total

    if not invoice_number:
        invoice_number = f"INV-{order.order_number}-{uuid4().hex[:4].upper()}"

    invoice = SalesInvoice(
        invoice_number=invoice_number,
        order_id=order.id,
        contact_id=order.contact_id,
        status=SalesInvoiceStatus.DRAFT,
        issue_date=date.today(),
        due_date=due_date or date.today(),
        currency=order.currency,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=grand_total,
        lines=invoice_lines,
    )

    session.add(invoice)
    await session.flush()
    await session.refresh(invoice)
    return invoice


async def create_adhoc_invoice(
    session: AsyncSession,
    contact_id: UUID,
    lines: list[dict],
    invoice_number: str | None = None,
    due_date: date | None = None,
    currency: str = "EGP",
    default_tax_rate: Decimal = Decimal("0.1400"),
) -> SalesInvoice:
    """
    Creates a DRAFT SalesInvoice with no preceding SalesOrder (order_id=None).

    For direct/ad-hoc billing flows that have no order-fulfillment step of
    their own — service verticals like Hospitality (folio checkout) and
    Vehicle Rental (rental agreement close-out), or any manual invoice a
    merchant wants to raise without going through Sales Orders.

    `lines` is a list of dicts: {item_id, qty, unit_price, variant_id?,
    uom_id?, tax_rate?}. Each is validated and totalled the same way
    generate_invoice_from_order() totals fulfilled order lines.
    """
    if not lines:
        raise ValueError("Cannot create an invoice with no lines.")

    invoice_lines: list[SalesInvoiceLine] = []
    subtotal = Decimal("0.0000")
    tax_total = Decimal("0.0000")

    for raw_line in lines:
        qty = Decimal(str(raw_line["qty"]))
        unit_price = Decimal(str(raw_line["unit_price"]))
        if qty <= 0:
            raise ValueError("Line quantity must be positive.")
        if unit_price < 0:
            raise ValueError("Line unit price cannot be negative.")

        tax_rate = Decimal(str(raw_line.get("tax_rate", default_tax_rate)))
        line_total = (qty * unit_price).quantize(Decimal("0.0001"))
        tax_amount = (line_total * tax_rate).quantize(Decimal("0.0001"))

        invoice_lines.append(
            SalesInvoiceLine(
                item_id=raw_line["item_id"],
                variant_id=raw_line.get("variant_id"),
                uom_id=raw_line.get("uom_id"),
                qty=qty,
                unit_price=unit_price,
                line_total=line_total,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
            )
        )
        subtotal += line_total
        tax_total += tax_amount

    grand_total = subtotal + tax_total

    if not invoice_number:
        invoice_number = f"INV-ADHOC-{uuid4().hex[:8].upper()}"

    invoice = SalesInvoice(
        invoice_number=invoice_number,
        order_id=None,
        contact_id=contact_id,
        status=SalesInvoiceStatus.DRAFT,
        issue_date=date.today(),
        due_date=due_date or date.today(),
        currency=currency,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=grand_total,
        lines=invoice_lines,
    )

    session.add(invoice)
    await session.flush()
    await session.refresh(invoice)
    return invoice


async def post_invoice(
    session: AsyncSession,
    invoice_id: UUID,
    tenant_id: UUID | str,
) -> SalesInvoice:
    """
    Posts a DRAFT invoice:
    1. Transitions invoice status to POSTED.
    2. Transitions linked SalesOrder to INVOICED.
    3. Emits 'sales.invoice_posted' Domain Event to the Outbox table within the same transaction.
    """
    stmt = (
        select(SalesInvoice)
        .where(SalesInvoice.id == invoice_id)
        .options(selectinload(SalesInvoice.lines))
        .with_for_update()
    )
    res = await session.execute(stmt)
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise ValueError(f"SalesInvoice not found: {invoice_id}")

    if invoice.status != SalesInvoiceStatus.DRAFT:
        raise ValueError(
            f"Cannot post invoice in status {invoice.status}. Only DRAFT invoices can be posted."
        )

    # Transition invoice
    invoice.status = SalesInvoiceStatus.POSTED
    session.add(invoice)

    # Only ad-hoc-free invoices carry a linked SalesOrder to transition.
    # Ad-hoc invoices (order_id is None — e.g. Hospitality/Rental checkout)
    # skip this step entirely; there is no order to advance.
    if invoice.order_id is not None:
        order_stmt = (
            select(SalesOrder)
            .where(SalesOrder.id == invoice.order_id)
            .with_for_update()
        )
        order_res = await session.execute(order_stmt)
        order = order_res.scalar_one_or_none()
        if not order:
            raise ValueError(f"Linked SalesOrder not found: {invoice.order_id}")

        order.status = SalesOrderStatus.INVOICED
        session.add(order)

    # Determine tenant_id for event envelope
    #
    # BUG (found via live WhatsApp verification, 11 Sep 2026): this used to
    # read a module-level ContextVar named `current_tenant` from
    # app.core.db.context — but that module only ever defined
    # `current_tenant_id` (see its docstring), and nothing in the codebase
    # ever set it regardless of the name. The `from ... import current_tenant`
    # line therefore always raised ImportError, which the bare
    # `except (ImportError, Exception): tenant_id = "system"` silently
    # swallowed — so every single `sales.invoice_posted` event, for every
    # tenant, was published with tenant_id="system". Downstream consumers
    # (the accounting GL Bridge in app.modules.accounting.consumers.events,
    # and app.plugins.whatsapp.listeners.handle_invoice_posted_whatsapp)
    # then tried to open a tenant_session for the literal tenant "system",
    # which resolves to schema "tenant_system" — a schema that doesn't
    # exist — and failed with
    # `asyncpg.exceptions.UndefinedTableError: relation "tenant_system.contacts"
    # does not exist`, swallowed by the EventBus and logged only as a
    # warning. So every invoice ever posted through this endpoint silently
    # never reached accounting or WhatsApp. Fixed by taking tenant_id as an
    # explicit parameter from the caller (the router already has it via
    # CurrentUser) instead of any ContextVar.
    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="sales.invoice_posted",
        tenant_id=str(tenant_id),
        payload={
            "id": str(invoice.id),
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "order_id": str(invoice.order_id) if invoice.order_id else None,
            "contact_id": str(invoice.contact_id),
            "subtotal": str(invoice.subtotal),
            "tax_total": str(invoice.tax_total),
            "grand_total": str(invoice.grand_total),
            "issue_date": invoice.issue_date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "currency": invoice.currency,
            "lines": [
                {
                    "item_id": str(line.item_id),
                    "variant_id": str(line.variant_id) if line.variant_id else None,
                    "uom_id": str(line.uom_id) if line.uom_id else None,
                    "qty": str(line.qty),
                    "unit_price": str(line.unit_price),
                    "line_total": str(line.line_total),
                    "tax_rate": str(line.tax_rate),
                    "tax_amount": str(line.tax_amount),
                }
                for line in invoice.lines
            ],
        },
    )
    await event_bus.publish(event, session=session)

    await session.flush()
    await session.refresh(invoice)
    return invoice
