from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.modules.inventory.models.core import (
    CostConsumption,
    SerialState,
    StockMovement,
)
from app.modules.inventory.services.costing import CostingRequest, consume_stock
from app.modules.inventory.services.reservation import release_reservation
from app.modules.inventory.services.serial_lifecycle import transition_serial_state
from app.modules.sales.models.core import SalesOrder, SalesOrderStatus


@dataclass
class FulfillmentResult:
    order: SalesOrder
    movements: list[StockMovement]
    consumptions: list[CostConsumption]

    def __iter__(self):
        return iter((self.order, self.movements, self.consumptions))


async def fulfill_sales_order(
    session: AsyncSession,
    order_id: UUID,
    warehouse_id: UUID,
    fulfillment_lines: list[dict[str, Any]],
) -> FulfillmentResult:
    """
    Fulfills a CONFIRMED or PARTIALLY_FULFILLED SalesOrder.
    For each fulfillment line:
      1. Releases reserved stock in the Item's base unit.
      2. Consumes stock via the Costing Engine using movement_type="SALES_ISSUE".
      3. For serialized items, transitions serial state to SOLD and binds owner contact.
      4. Updates line fulfilled_qty and overall SalesOrder status (FULFILLED or PARTIALLY_FULFILLED).
    """
    if not fulfillment_lines:
        raise ValueError("fulfillment_lines cannot be empty")

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

    if order.status not in (SalesOrderStatus.CONFIRMED, SalesOrderStatus.PARTIALLY_FULFILLED):
        raise ValueError(
            f"Cannot fulfill sales order in status {order.status}. "
            "Order must be CONFIRMED or PARTIALLY_FULFILLED."
        )

    all_movements: list[StockMovement] = []
    all_consumptions: list[CostConsumption] = []

    for fl in fulfillment_lines:
        line_id_val = fl.get("line_id")
        item_id_val = fl.get("item_id")
        line = None

        if line_id_val:
            target_id = UUID(str(line_id_val))
            for ol in order.lines:
                if ol.id == target_id:
                    line = ol
                    break
        elif item_id_val:
            target_item_id = UUID(str(item_id_val))
            target_variant_id = UUID(str(fl["variant_id"])) if fl.get("variant_id") else None
            for ol in order.lines:
                if (
                    ol.item_id == target_item_id
                    and ol.variant_id == target_variant_id
                    and (ol.qty - ol.fulfilled_qty) > 0
                ):
                    line = ol
                    break

        if not line:
            raise ValueError(
                f"Order line not found in sales order {order_id} for fulfillment payload {fl}"
            )

        qty = Decimal(str(fl["qty"]))
        if qty <= 0:
            raise ValueError("Fulfillment quantity must be strictly positive")

        if line.fulfilled_qty + qty > line.qty:
            raise ValueError(
                f"Fulfillment quantity {qty} exceeds remaining ordered quantity "
                f"{(line.qty - line.fulfilled_qty)} for line {line.id}"
            )

        serial_id = UUID(str(fl["serial_id"])) if fl.get("serial_id") else None
        batch_id = UUID(str(fl["batch_id"])) if fl.get("batch_id") else None
        uom_id = UUID(str(fl["uom_id"])) if fl.get("uom_id") else line.uom_id

        # Hook 1 (Release): Release reservation on the general stock pool (base UoM conversion handled in service)
        await release_reservation(
            session=session,
            item_id=line.item_id,
            warehouse_id=warehouse_id,
            qty=qty,
            variant_id=line.variant_id,
            uom_id=uom_id,
        )

        # Hook 2 (Consume): Invoke consume_stock with SALES_ISSUE
        req = CostingRequest(
            item_id=line.item_id,
            variant_id=line.variant_id,
            warehouse_id=warehouse_id,
            quantity=qty,
            movement_type="SALES_ISSUE",
            batch_id=batch_id,
            serial_id=serial_id,
            uom_id=uom_id,
            reference_id=str(order.id),
            contact_id=order.contact_id,
        )
        mvts, cons = await consume_stock(session=session, requests=[req])
        all_movements.extend(mvts)
        all_consumptions.extend(cons)

        # Hook 3 (Serial Lifecycle): Update SerialNumber to SOLD and assign current owner
        if serial_id:
            await transition_serial_state(
                session=session,
                serial_id=serial_id,
                new_state=SerialState.SOLD,
                contact_id=order.contact_id,
            )

        line.fulfilled_qty += qty
        session.add(line)

    if all(ol.fulfilled_qty >= ol.qty for ol in order.lines):
        order.status = SalesOrderStatus.FULFILLED
    elif any(ol.fulfilled_qty > 0 for ol in order.lines):
        order.status = SalesOrderStatus.PARTIALLY_FULFILLED

    session.add(order)
    await session.flush()
    await session.refresh(order)

    return FulfillmentResult(
        order=order,
        movements=all_movements,
        consumptions=all_consumptions,
    )
