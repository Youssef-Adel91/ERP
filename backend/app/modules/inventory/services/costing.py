import logging
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.inventory.models import (
    Batch,
    CostConsumption,
    CostingMethod,
    CostLayer,
    Item,
    StockLevel,
    StockMovement,
    UnitOfMeasure,
)

logger = logging.getLogger(__name__)


@dataclass
class CostingRequest:
    item_id: UUID
    variant_id: UUID | None
    warehouse_id: UUID
    quantity: Decimal
    movement_type: str
    batch_id: UUID | None = None
    serial_id: UUID | None = None
    uom_id: UUID | None = None
    reference_id: str | None = None
    contact_id: UUID | None = None


def _apply_consumption(
    session: AsyncSession,
    item: Item,
    quantity_to_consume: Decimal,
    movement: StockMovement,
    open_layers: list[CostLayer],
    requires_serial: bool = False,
) -> list[CostConsumption]:
    """
    Core algorithm to apply a consumption quantity against open layers.
    Does not flush or commit. Returns the new CostConsumption records.
    """
    consumptions = []
    total_open_qty = sum(layer.qty_remaining for layer in open_layers)
    remaining_qty_to_consume = quantity_to_consume

    if remaining_qty_to_consume > total_open_qty:
        shortfall = remaining_qty_to_consume - total_open_qty

        if requires_serial:
            raise ValueError(f"Provisional layer blocked for serialized Item {movement.item_id}")

        last_known_cost = Decimal("0")
        if open_layers:
            last_known_cost = open_layers[-1].unit_cost_current

        provisional_layer = CostLayer(
            item_id=movement.item_id,
            variant_id=movement.variant_id,
            warehouse_id=movement.warehouse_id,
            batch_id=movement.batch_id,
            serial_id=movement.serial_id,
            qty_received=shortfall,
            qty_remaining=shortfall,
            unit_cost_original=last_known_cost,
            unit_cost_current=last_known_cost,
            is_provisional=True,
            received_at=movement.occurred_at,
        )
        session.add(provisional_layer)
        open_layers.append(provisional_layer)
        total_open_qty += shortfall
        logger.warning(
            f"Created provisional layer for Item {movement.item_id} (Shortfall: {shortfall})"
        )

    if item.costing_method == CostingMethod.WAC:
        for layer in open_layers:
            if remaining_qty_to_consume <= 0:
                break

            proportion = layer.qty_remaining / total_open_qty
            qty_to_consume_from_layer = layer.qty_remaining.min(proportion * quantity_to_consume)

            if layer == open_layers[-1]:
                qty_to_consume_from_layer = remaining_qty_to_consume

            layer.qty_remaining -= qty_to_consume_from_layer
            remaining_qty_to_consume -= qty_to_consume_from_layer

            consumption = CostConsumption(
                layer_id=layer.id,
                movement_id=movement.id,
                qty_consumed=qty_to_consume_from_layer,
                unit_cost_at_consumption=layer.unit_cost_current,
            )
            session.add(consumption)
            consumptions.append(consumption)

    else:
        for layer in open_layers:
            if remaining_qty_to_consume <= 0:
                break

            qty_to_consume_from_layer = layer.qty_remaining.min(remaining_qty_to_consume)

            layer.qty_remaining -= qty_to_consume_from_layer
            remaining_qty_to_consume -= qty_to_consume_from_layer

            consumption = CostConsumption(
                layer_id=layer.id,
                movement_id=movement.id,
                qty_consumed=qty_to_consume_from_layer,
                unit_cost_at_consumption=layer.unit_cost_current,
            )
            session.add(consumption)
            consumptions.append(consumption)

    return consumptions


async def consume_stock(
    session: AsyncSession,
    requests: list[CostingRequest],
) -> tuple[list[StockMovement], list[CostConsumption]]:
    """
    Consumes inventory using FIFO or WAC algorithms.
    Acquires deterministic row-level locks on StockLevel to prevent deadlocks (FR-333).
    Handles negative stock with provisional layers (FR-331).
    """
    if not requests:
        return []

    sorted_requests = sorted(
        requests,
        key=lambda r: (str(r.item_id), str(r.variant_id or ""), str(r.warehouse_id), str(r.batch_id or ""), str(r.serial_id or "")),
    )

    movements = []
    consumptions_out = []

    for req in sorted_requests:
        qty_to_consume = req.quantity
        if req.uom_id:
            uom = await session.get(UnitOfMeasure, req.uom_id)
            if uom:
                qty_to_consume = req.quantity * uom.conversion_factor

        stmt = (
            select(StockLevel)
            .where(
                StockLevel.item_id == req.item_id,
                StockLevel.variant_id == req.variant_id,
                StockLevel.warehouse_id == req.warehouse_id,
                StockLevel.batch_id == req.batch_id,
                StockLevel.serial_id == req.serial_id,
            )
            .with_for_update()
        )

        result = await session.execute(stmt)
        stock_level = result.scalar_one_or_none()

        item_stmt = select(Item).where(Item.id == req.item_id)
        item = (await session.execute(item_stmt)).scalar_one()

        if item.requires_serial:
            if not req.serial_id:
                raise ValueError(f"serial_id is required for serialized item {item.id}")
            if abs(qty_to_consume) != Decimal("1"):
                raise ValueError(f"Quantity must be 1 or -1 for serialized item {item.id}")

        if item.requires_batch:
            if not req.batch_id:
                raise ValueError(f"batch_id is required for batched item {item.id}")
            
        if req.batch_id:
            batch = await session.get(Batch, req.batch_id)
            if batch and batch.expiry_date and batch.expiry_date < datetime.now(UTC).date():
                raise ValueError(f"Batch {req.batch_id} is expired and cannot be consumed")

        if not stock_level:
            stock_level = StockLevel(
                item_id=req.item_id,
                variant_id=req.variant_id,
                warehouse_id=req.warehouse_id,
                batch_id=req.batch_id,
                serial_id=req.serial_id,
                quantity=Decimal("0"),
            )
            session.add(stock_level)
            await session.flush()

        movement = StockMovement(
            item_id=req.item_id,
            variant_id=req.variant_id,
            warehouse_id=req.warehouse_id,
            batch_id=req.batch_id,
            serial_id=req.serial_id,
            qty=-qty_to_consume,
            movement_type=req.movement_type,
            reference_id=req.reference_id,
            contact_id=req.contact_id,
        )
        session.add(movement)
        await session.flush()
        
        movements.append(movement)

        open_layers_stmt = (
            select(CostLayer)
            .where(
                CostLayer.item_id == req.item_id,
                CostLayer.variant_id == req.variant_id,
                CostLayer.warehouse_id == req.warehouse_id,
                CostLayer.batch_id == req.batch_id,
                CostLayer.serial_id == req.serial_id,
                CostLayer.qty_remaining > 0,
                CostLayer.received_at <= movement.occurred_at
            )
            .order_by(CostLayer.received_at.asc(), CostLayer.sequence_no.asc())
        )

        open_layers_result = await session.execute(open_layers_stmt)
        open_layers = list(open_layers_result.scalars().all())

        new_consumptions = _apply_consumption(session, item, qty_to_consume, movement, open_layers, requires_serial=item.requires_serial)
        consumptions_out.extend(new_consumptions)

        stock_level.quantity -= qty_to_consume

    return movements, consumptions_out


async def consume_stock_fifo(
    session: AsyncSession,
    item_id: UUID,
    warehouse_id: UUID,
    qty_to_consume: Decimal
):
    """
    Consumes stock using FIFO valuation against models/core.py's CostLayer
    (the canonical cost-layer model — see models/stock.py's module docstring
    for why the former duplicate model is no longer used here).
    Returns a list of tuples containing (CostLayer, qty_consumed_from_layer).
    """
    from app.modules.inventory.exceptions import InsufficientStockError

    if qty_to_consume <= 0:
        return []

    # Query active layers ordered by received_at ASC for FIFO
    result = await session.execute(
        select(CostLayer)
        .where(
            CostLayer.item_id == item_id,
            CostLayer.warehouse_id == warehouse_id,
            CostLayer.qty_remaining > 0
        )
        .order_by(CostLayer.received_at.asc(), CostLayer.sequence_no.asc())
        .with_for_update()
    )

    available_layers = result.scalars().all()

    total_available = sum((layer.qty_remaining for layer in available_layers), Decimal("0"))
    if qty_to_consume > total_available:
        raise InsufficientStockError(
            f"Cannot consume {qty_to_consume} units. Only {total_available} available in warehouse."
        )

    consumed_details = []
    remaining_to_consume = qty_to_consume

    for layer in available_layers:
        if remaining_to_consume <= 0:
            break

        qty_from_layer = min(remaining_to_consume, layer.qty_remaining)

        layer.qty_remaining -= qty_from_layer
        remaining_to_consume -= qty_from_layer

        consumed_details.append((layer, qty_from_layer))
        session.add(layer)

    return consumed_details
