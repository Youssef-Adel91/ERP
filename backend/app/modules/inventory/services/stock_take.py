from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.events.event_bus import get_event_bus, DomainEvent
from app.modules.inventory.models.core import CostLayer, Item, StockLevel, StockMovement
from app.modules.inventory.models.stock_take import StockTake, StockTakeLine, StockTakeStatus
from app.modules.inventory.services.costing import CostingRequest, consume_stock


async def start_count(session: AsyncSession, stock_take_id: UUID) -> StockTake:
    """
    Transitions a StockTake to COUNTING status and snapshots current StockLevels
    into StockTakeLines.
    """
    stock_take = await session.get(StockTake, stock_take_id)
    if not stock_take:
        raise ValueError(f"StockTake {stock_take_id} not found")

    if stock_take.status != StockTakeStatus.DRAFT:
        raise ValueError(f"StockTake {stock_take_id} cannot be started from status {stock_take.status}")

    stock_take.status = StockTakeStatus.COUNTING

    # Snapshot existing stock
    stmt = select(StockLevel).where(
        StockLevel.warehouse_id == stock_take.warehouse_id,
        StockLevel.quantity > 0
    )
    result = await session.execute(stmt)
    stock_levels = result.scalars().all()

    for level in stock_levels:
        line = StockTakeLine(
            stock_take_id=stock_take.id,
            item_id=level.item_id,
            variant_id=level.variant_id,
            batch_id=level.batch_id,
            serial_id=level.serial_id,
            expected_qty=level.quantity,
        )
        session.add(line)

    session.add(stock_take)
    return stock_take


async def get_blind_count_sheet(session: AsyncSession, stock_take_id: UUID) -> list[dict]:
    """
    Returns the count sheet for a StockTake, masking the expected_qty to enforce blind counting.
    """
    stmt = select(StockTakeLine).where(StockTakeLine.stock_take_id == stock_take_id)
    result = await session.execute(stmt)
    lines = result.scalars().all()

    sheet = []
    for line in lines:
        sheet.append({
            "line_id": line.id,
            "item_id": line.item_id,
            "variant_id": line.variant_id,
            "batch_id": line.batch_id,
            "serial_id": line.serial_id,
            # Masking expected_qty for blind counting
            "expected_qty": None,
            "counted_qty": line.counted_qty,
        })
    return sheet


async def record_count(session: AsyncSession, stock_take_id: UUID, counts: list[dict]):
    """
    Records physical counts against the stock take lines.
    Allows injecting new lines if unexpected stock is found (expected_qty=0).
    """
    stock_take = await session.get(StockTake, stock_take_id)
    if not stock_take or stock_take.status != StockTakeStatus.COUNTING:
        raise ValueError("StockTake must be in COUNTING status to record counts")

    for payload in counts:
        line_id = payload.get("line_id")
        counted_qty = Decimal(str(payload.get("counted_qty", 0)))
        
        if line_id:
            line = await session.get(StockTakeLine, line_id)
            if line:
                line.counted_qty = counted_qty
                line.variance_qty = line.counted_qty - line.expected_qty
                session.add(line)
        else:
            # New unexpected stock found during count
            line = StockTakeLine(
                stock_take_id=stock_take.id,
                item_id=payload["item_id"],
                variant_id=payload.get("variant_id"),
                batch_id=payload.get("batch_id"),
                serial_id=payload.get("serial_id"),
                expected_qty=Decimal("0"),
                counted_qty=counted_qty,
                variance_qty=counted_qty,
            )
            session.add(line)
            
    # Move to REVIEW after counting is recorded
    stock_take.status = StockTakeStatus.REVIEW
    session.add(stock_take)


async def post_stock_take(session: AsyncSession, stock_take_id: UUID):
    """
    Posts the stock take. Resolves all variances using the Costing Engine.
    Emits an Outbox event for the Accounting Module.
    """
    stock_take = await session.get(StockTake, stock_take_id)
    if not stock_take or stock_take.status != StockTakeStatus.REVIEW:
        raise ValueError("StockTake must be in REVIEW status to post")

    stmt = select(StockTakeLine).where(StockTakeLine.stock_take_id == stock_take_id)
    result = await session.execute(stmt)
    lines = result.scalars().all()

    total_loss = Decimal("0")
    total_gain = Decimal("0")

    for line in lines:
        if line.variance_qty is None:
            raise ValueError(f"Line {line.id} was not counted. Cannot post.")

        if line.variance_qty == 0:
            continue

        if line.variance_qty < 0:
            # Shrinkage: Deduct via consume_stock
            req = CostingRequest(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=stock_take.warehouse_id,
                quantity=abs(line.variance_qty),
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                movement_type="STOCK_TAKE_LOSS",
                reference_id=stock_take.reference_id,
            )
            # This handles reducing stock_level and closing cost layers.
            await consume_stock(session, [req])
            total_loss += abs(line.variance_qty)

        elif line.variance_qty > 0:
            # Gain: Increment stock and create a new cost layer
            item = await session.get(Item, line.item_id)
            
            # Use unit_cost if provided, else fallback to last known cost, else 0
            if line.unit_cost is not None:
                cost = line.unit_cost
            else:
                last_layer_stmt = (
                    select(CostLayer)
                    .where(CostLayer.item_id == line.item_id)
                    .order_by(CostLayer.received_at.desc())
                    .limit(1)
                )
                last_layer = (await session.execute(last_layer_stmt)).scalar_one_or_none()
                cost = last_layer.unit_cost_current if last_layer else Decimal("0")

            # 1. Ensure StockLevel exists and update
            level_stmt = (
                select(StockLevel)
                .where(
                    StockLevel.item_id == line.item_id,
                    StockLevel.variant_id == line.variant_id,
                    StockLevel.warehouse_id == stock_take.warehouse_id,
                    StockLevel.batch_id == line.batch_id,
                    StockLevel.serial_id == line.serial_id,
                )
                .with_for_update()
            )
            stock_level = (await session.execute(level_stmt)).scalar_one_or_none()
            
            if not stock_level:
                stock_level = StockLevel(
                    item_id=line.item_id,
                    variant_id=line.variant_id,
                    warehouse_id=stock_take.warehouse_id,
                    batch_id=line.batch_id,
                    serial_id=line.serial_id,
                    quantity=line.variance_qty
                )
            else:
                stock_level.quantity += line.variance_qty
            session.add(stock_level)
            
            # 2. Record StockMovement
            movement = StockMovement(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=stock_take.warehouse_id,
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                qty=line.variance_qty,
                movement_type="STOCK_TAKE_GAIN",
                reference_id=stock_take.reference_id,
            )
            session.add(movement)
            await session.flush()
            
            # 3. Create CostLayer
            layer = CostLayer(
                item_id=line.item_id,
                variant_id=line.variant_id,
                warehouse_id=stock_take.warehouse_id,
                batch_id=line.batch_id,
                serial_id=line.serial_id,
                unit_cost_original=cost,
                unit_cost_current=cost,
                qty_received=line.variance_qty,
                qty_remaining=line.variance_qty,
            )
            session.add(layer)
            total_gain += line.variance_qty

    stock_take.status = StockTakeStatus.POSTED
    session.add(stock_take)

    # Emit outbox event for accounting module
    # Note: Event schema will need a tenant_id. We fetch ambient if context exists.
    try:
        # Standard omni-erp pattern for ambient tenant
        from app.core.db.context import current_tenant
        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        tenant_id = "system"

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="inventory.stock_take_posted",
        tenant_id=str(tenant_id),
        payload={
            "stock_take_id": str(stock_take.id),
            "warehouse_id": str(stock_take.warehouse_id),
            "total_loss_qty": str(total_loss),
            "total_gain_qty": str(total_gain),
            "reference_id": stock_take.reference_id,
        }
    )
    await event_bus.publish(event, session=session)

    return stock_take
