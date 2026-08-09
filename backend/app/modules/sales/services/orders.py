from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.modules.inventory.services.pricing import get_item_price
from app.modules.inventory.services.reservation import reserve_stock
from app.modules.sales.models.core import SalesOrder, SalesOrderLine, SalesOrderStatus


async def create_sales_order(
    session: AsyncSession,
    contact_id: UUID,
    lines_data: list[dict],
    order_date: date | None = None,
    currency: str = "EGP",
    price_list_id: UUID | None = None,
    order_number: str | None = None,
) -> SalesOrder:
    """
    Creates a new SalesOrder in DRAFT status.
    Uses the Inventory Pricing interface (get_item_price) to price any lines
    where unit_price is not explicitly overridden.
    """
    if not lines_data:
        raise ValueError("Sales order must contain at least one line")

    if not order_number:
        order_number = f"SO-{uuid4().hex[:8].upper()}"

    order = SalesOrder(
        contact_id=contact_id,
        order_number=order_number,
        status=SalesOrderStatus.DRAFT,
        order_date=order_date or date.today(),
        currency=currency,
        total_amount=Decimal("0.0000"),
    )
    session.add(order)
    await session.flush()

    total_amount = Decimal("0.0000")
    for line_dict in lines_data:
        item_id = line_dict["item_id"]
        if isinstance(item_id, str):
            item_id = UUID(item_id)
        qty = Decimal(str(line_dict["qty"]))
        variant_id = line_dict.get("variant_id")
        if isinstance(variant_id, str):
            variant_id = UUID(variant_id)
        uom_id = line_dict.get("uom_id")
        if isinstance(uom_id, str):
            uom_id = UUID(uom_id)
        unit_price = line_dict.get("unit_price")

        if unit_price is None:
            unit_price = await get_item_price(
                session=session,
                item_id=item_id,
                price_list_id=price_list_id,
                variant_id=variant_id,
                qty=qty,
                uom_id=uom_id,
            )
        else:
            unit_price = Decimal(str(unit_price))

        line_total = qty * unit_price
        total_amount += line_total

        line = SalesOrderLine(
            order_id=order.id,
            item_id=item_id,
            variant_id=variant_id,
            uom_id=uom_id,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
        )
        session.add(line)

    order.total_amount = total_amount
    session.add(order)
    await session.flush()
    await session.refresh(order)

    # Reload with lines relationship populated
    stmt = (
        select(SalesOrder)
        .where(SalesOrder.id == order.id)
        .options(selectinload(SalesOrder.lines))
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def confirm_sales_order(
    session: AsyncSession,
    order_id: UUID,
    warehouse_id: UUID,
) -> SalesOrder:
    """
    Confirms a Sales Order (DRAFT -> CONFIRMED).
    Iterates through order lines and invokes reserve_stock from the Inventory module,
    passing the line uom_id so UoM conversions are natively handled.
    If reserve_stock raises an exception (e.g. InsufficientStockError), the transaction aborts.
    """
    stmt = (
        select(SalesOrder)
        .where(SalesOrder.id == order_id)
        .options(selectinload(SalesOrder.lines))
        .with_for_update()
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order:
        raise ValueError(f"Sales order {order_id} not found")

    if order.status != SalesOrderStatus.DRAFT:
        raise ValueError(f"Cannot confirm sales order in status {order.status}")

    for line in order.lines:
        await reserve_stock(
            session=session,
            item_id=line.item_id,
            warehouse_id=warehouse_id,
            qty=line.qty,
            source_doc_id=str(order.id),
            variant_id=line.variant_id,
            uom_id=line.uom_id,
        )

    order.status = SalesOrderStatus.CONFIRMED
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order
