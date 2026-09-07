from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.inventory.models.core import (
    CostConsumption,
    CostLayer,
    SerialState,
    StockLevel,
    StockMovement,
    UnitOfMeasure,
)
from app.modules.inventory.services.serial_lifecycle import (
    transition_serial_state,
    validate_sales_return,
)
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.sales.models.returns import (
    SalesReturn,
    SalesReturnLine,
    SalesReturnStatus,
)


async def create_sales_return(
    session: AsyncSession,
    invoice_id: UUID,
    contact_id: UUID,
    lines_data: list[dict],
    order_id: UUID | None = None,
) -> SalesReturn:
    """
    Creates a new SalesReturn in DRAFT status linked to an original SalesInvoice.
    """
    invoice = await session.get(SalesInvoice, invoice_id)
    if not invoice:
        raise ValueError(f"Original SalesInvoice not found: {invoice_id}")

    target_order_id = order_id or invoice.order_id
    return_number = f"RET-{uuid4().hex[:8].upper()}"

    if not lines_data:
        raise ValueError("SalesReturn must contain at least one line")

    subtotal = Decimal("0.0000")
    tax_total = Decimal("0.0000")
    return_lines: list[SalesReturnLine] = []

    for idx, ld in enumerate(lines_data):
        orig_line_id = ld.get("original_invoice_line_id")
        if not orig_line_id:
            raise ValueError(f"Line {idx} missing required 'original_invoice_line_id'")

        qty = Decimal(str(ld["qty"]))
        if qty <= 0:
            raise ValueError(f"Return quantity must be strictly positive for line {idx}")

        unit_price = Decimal(str(ld["unit_price"]))
        line_total = qty * unit_price
        tax_rate = Decimal(str(ld.get("tax_rate", "0.1400")))
        tax_amount = line_total * tax_rate

        subtotal += line_total
        tax_total += tax_amount

        line = SalesReturnLine(
            original_invoice_line_id=UUID(str(orig_line_id)),
            item_id=UUID(str(ld["item_id"])),
            variant_id=UUID(str(ld["variant_id"])) if ld.get("variant_id") else None,
            uom_id=UUID(str(ld["uom_id"])) if ld.get("uom_id") else None,
            batch_id=UUID(str(ld["batch_id"])) if ld.get("batch_id") else None,
            serial_id=UUID(str(ld["serial_id"])) if ld.get("serial_id") else None,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
        )
        return_lines.append(line)

    grand_total = subtotal + tax_total

    sales_return = SalesReturn(
        return_number=return_number,
        order_id=target_order_id,
        invoice_id=invoice_id,
        contact_id=contact_id,
        status=SalesReturnStatus.DRAFT,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=grand_total,
        lines=return_lines,
    )
    session.add(sales_return)
    await session.flush()
    await session.refresh(sales_return)
    return sales_return


async def _latest_cost_layer_unit_cost(session: AsyncSession, item_id: UUID) -> Decimal:
    """
    Fallback historical-cost lookup for process_sales_return() when no matching
    CostConsumption records exist for the original sale (e.g. the invoice was
    ad-hoc with no SalesOrder to key the SALES_ISSUE movement off of, so Hook 2's
    primary lookup can't run at all).

    Bug fixed here: the previous code referenced `item.standard_cost`, a field
    that has never existed on the `Item` model (models/core.py) — every return
    that hit this fallback crashed with AttributeError. There is no per-item
    "standard cost" concept anywhere else in this codebase; the real source of
    truth for unit cost is CostLayer (the same table this function reads from
    for the primary lookup and writes to a few lines below for the new inbound
    layer). So instead we fall back to the most recently received CostLayer for
    this item, across any warehouse/batch/serial, as the best available estimate
    of what it actually cost. Returns 0 (previous silent-zero behavior preserved)
    if the item has no CostLayer history at all.
    """
    stmt = (
        select(CostLayer)
        .where(CostLayer.item_id == item_id)
        .order_by(CostLayer.received_at.desc())
        .limit(1)
    )
    latest_layer = (await session.execute(stmt)).scalar_one_or_none()
    return latest_layer.unit_cost_current if latest_layer else Decimal("0.0000")


async def process_sales_return(
    session: AsyncSession,
    return_id: UUID,
    warehouse_id: UUID,
) -> SalesReturn:
    """
    Processes a DRAFT SalesReturn:
    1. Hook 1 (Fraud Prevention): Validates serial number ownership via validate_sales_return.
    2. Hook 2 (Exact Cost Reversal): Extracts historical unit cost from CostConsumption records of the SALES_ISSUE movement and generates inbound CostLayer and StockMovement.
    3. Hook 3 (Serial Lifecycle): Transitions returned serial numbers to RETURNED state.
    """
    return_obj = await session.get(SalesReturn, return_id)
    if not return_obj:
        raise ValueError(f"SalesReturn not found: {return_id}")

    if return_obj.status != SalesReturnStatus.DRAFT:
        raise ValueError(
            f"Cannot process SalesReturn in status {return_obj.status}. Only DRAFT returns can be processed."
        )

    target_order_id = return_obj.order_id
    if not target_order_id:
        invoice = await session.get(SalesInvoice, return_obj.invoice_id)
        if invoice:
            target_order_id = invoice.order_id

    for line in return_obj.lines:
        # Hook 1: Fraud Prevention for Serialized Items
        if line.serial_id:
            await validate_sales_return(
                session=session,
                serial_id=line.serial_id,
                returning_contact_id=return_obj.contact_id,
            )

        # Hook 2: Exact Cost Reversal
        historical_unit_cost = Decimal("0.0000")
        if target_order_id:
            stmt = (
                select(CostConsumption)
                .join(StockMovement, CostConsumption.movement_id == StockMovement.id)
                .where(
                    StockMovement.item_id == line.item_id,
                    StockMovement.movement_type == "SALES_ISSUE",
                    StockMovement.reference_id == str(target_order_id),
                )
            )
            if line.variant_id:
                stmt = stmt.where(StockMovement.variant_id == line.variant_id)
            if line.serial_id:
                stmt = stmt.where(StockMovement.serial_id == line.serial_id)
            if line.batch_id:
                stmt = stmt.where(StockMovement.batch_id == line.batch_id)

            consumptions = (await session.execute(stmt)).scalars().all()
            if consumptions:
                total_cost = sum(
                    c.qty_consumed * c.unit_cost_at_consumption for c in consumptions
                )
                total_qty = sum(c.qty_consumed for c in consumptions)
                if total_qty > 0:
                    historical_unit_cost = total_cost / total_qty
            else:
                historical_unit_cost = await _latest_cost_layer_unit_cost(session, line.item_id)
        else:
            historical_unit_cost = await _latest_cost_layer_unit_cost(session, line.item_id)

        # UoM Conversion to Base Unit
        base_qty = line.qty
        if line.uom_id:
            uom = await session.get(UnitOfMeasure, line.uom_id)
            if uom:
                base_qty = line.qty * uom.conversion_factor

        # Create inbound StockMovement
        movement = StockMovement(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=warehouse_id,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            qty=base_qty,
            movement_type="SALES_RETURN",
            reference_id=str(return_obj.id),
            contact_id=return_obj.contact_id,
        )
        session.add(movement)

        # Create inbound CostLayer at exact historical unit cost
        layer = CostLayer(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=warehouse_id,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            qty_received=base_qty,
            qty_remaining=base_qty,
            unit_cost_original=historical_unit_cost,
            unit_cost_current=historical_unit_cost,
        )
        session.add(layer)

        # Update StockLevel in warehouse
        level_stmt = (
            select(StockLevel)
            .where(
                StockLevel.item_id == line.item_id,
                StockLevel.variant_id == line.variant_id,
                StockLevel.warehouse_id == warehouse_id,
                StockLevel.batch_id == line.batch_id,
                StockLevel.serial_id == line.serial_id,
            )
            .with_for_update()
        )
        level_res = await session.execute(level_stmt)
        stock_level = level_res.scalar_one_or_none()
        if stock_level:
            stock_level.quantity += base_qty
        else:
            stock_level = StockLevel(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=warehouse_id,
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                quantity=base_qty,
                qty_reserved=Decimal("0"),
            )
        session.add(stock_level)

        # Hook 3: Serial Lifecycle State Transition
        if line.serial_id:
            await transition_serial_state(
                session=session,
                serial_id=line.serial_id,
                new_state=SerialState.RETURNED,
                contact_id=None,
            )

    return_obj.status = SalesReturnStatus.RECEIVED
    session.add(return_obj)
    await session.flush()
    await session.refresh(return_obj)
    return return_obj


async def post_credit_note(
    session: AsyncSession,
    return_id: UUID,
) -> SalesReturn:
    """
    Generates a Credit Note (negative invoice totals), transitions SalesReturn status to CREDITED,
    and publishes the atomic sales.credit_note_posted domain event via the Outbox.
    """
    return_obj = await session.get(SalesReturn, return_id)
    if not return_obj:
        raise ValueError(f"SalesReturn not found: {return_id}")

    if return_obj.status != SalesReturnStatus.RECEIVED:
        raise ValueError(
            f"Cannot post credit note for SalesReturn in status {return_obj.status}. Only RECEIVED returns can be credited."
        )

    credit_note_number = f"CN-{return_obj.return_number}"
    credit_note = SalesInvoice(
        invoice_number=credit_note_number,
        # Bug fixed here: SalesInvoice.order_id is a foreign key to
        # sales_orders.id, NOT a generic "originating document" pointer. The
        # previous `return_obj.order_id or return_obj.invoice_id` fallback
        # put the ORIGINAL SalesInvoice's id into this column whenever the
        # return had no real order (e.g. any ad-hoc invoice, which is common
        # — order_id is nullable precisely for that case) — violating the FK
        # constraint every time, confirmed live via
        # `sales_invoices_order_id_fkey` IntegrityError. There's no order to
        # link when there isn't one; leave it null. Traceability back to the
        # original invoice/return is already preserved via
        # SalesReturn.invoice_id and SalesReturn.credit_note_id, so nothing
        # is lost.
        order_id=return_obj.order_id,
        contact_id=return_obj.contact_id,
        status=SalesInvoiceStatus.POSTED,
        subtotal=-return_obj.subtotal,
        tax_total=-return_obj.tax_total,
        grand_total=-return_obj.grand_total,
    )
    session.add(credit_note)
    await session.flush()

    return_obj.status = SalesReturnStatus.CREDITED
    return_obj.credit_note_id = credit_note.id
    session.add(return_obj)

    try:
        from app.core.db.context import current_tenant

        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        tenant_id = "system"

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="sales.credit_note_posted",
        tenant_id=str(tenant_id),
        payload={
            "id": str(return_obj.id),
            "return_id": str(return_obj.id),
            "return_number": return_obj.return_number,
            "credit_note_id": str(credit_note.id),
            "invoice_id": str(return_obj.invoice_id),
            "order_id": str(return_obj.order_id) if return_obj.order_id else None,
            "contact_id": str(return_obj.contact_id),
            "subtotal": str(-return_obj.subtotal),
            "tax_total": str(-return_obj.tax_total),
            "grand_total": str(-return_obj.grand_total),
            "lines": [
                {
                    "item_id": str(line.item_id),
                    "variant_id": str(line.variant_id) if line.variant_id else None,
                    "uom_id": str(line.uom_id) if line.uom_id else None,
                    "qty": str(line.qty),
                    "unit_price": str(line.unit_price),
                    "line_total": str(-line.line_total),
                    "tax_rate": str(line.tax_rate),
                    "tax_amount": str(-line.tax_amount),
                }
                for line in return_obj.lines
            ],
        },
    )
    await event_bus.publish(event, session=session)

    await session.flush()
    await session.refresh(return_obj)
    return return_obj
