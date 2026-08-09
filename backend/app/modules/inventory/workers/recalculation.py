import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import select

from app.core.db.database import tenant_session
from app.core.events.event_bus import get_event_bus
from app.modules.accounting.models import AccountingPeriod
from app.modules.inventory.events import CogsVarianceAdjustedEvent
from app.modules.inventory.models import (
    CostConsumption,
    CostLayer,
    Item,
    StockLevel,
    StockMovement,
)
from app.modules.inventory.services.costing import _apply_consumption

logger = logging.getLogger(__name__)


async def recalculate_cost_from_date(
    ctx,
    tenant_id: UUID,
    item_id: UUID,
    warehouse_id: UUID,
    from_date: datetime,
    variant_id: UUID | None = None,
):
    """
    ARQ Background Job for Backdated Transaction Recalculation (FR-332).
    Chronologically replays stock movements to mathematically correct consumption layers.
    """
    logger.info(
        f"Starting recalculation for tenant={tenant_id}, item={item_id}, "
        f"warehouse={warehouse_id}, variant={variant_id}, from={from_date}",
    )

    async with tenant_session(tenant_id) as session:
        # 1. Closed Period Gate (FR-332)
        # Verify that from_date does not fall into a closed accounting period
        period_stmt = select(AccountingPeriod).where(
            AccountingPeriod.end_date >= from_date,
            AccountingPeriod.start_date <= datetime.utcnow(),
            AccountingPeriod.is_closed.is_(True),
        )
        closed_periods = (await session.execute(period_stmt)).scalars().all()
        if closed_periods:
            raise ValueError(
                f"Cannot recalculate costs from {from_date}: "
                f"History falls inside a closed accounting period.",
            )

        # 2. Acquire Granular StockLevel Lock
        lock_stmt = (
            select(StockLevel)
            .where(
                StockLevel.item_id == item_id,
                StockLevel.variant_id == variant_id,
                StockLevel.warehouse_id == warehouse_id,
            )
            .with_for_update()
        )
        stock_level = (await session.execute(lock_stmt)).scalar_one_or_none()
        if not stock_level:
            logger.info("No StockLevel found, nothing to recalculate.")
            return

        item = (await session.execute(select(Item).where(Item.id == item_id))).scalar_one()

        # 3. Fetch all StockMovements (OUT only) occurring on or after from_date
        movements_stmt = (
            select(StockMovement)
            .where(
                StockMovement.item_id == item_id,
                StockMovement.variant_id == variant_id,
                StockMovement.warehouse_id == warehouse_id,
                StockMovement.occurred_at >= from_date,
                StockMovement.movement_type == "OUT",
            )
            .order_by(StockMovement.occurred_at.asc())
        )
        movements = (await session.execute(movements_stmt)).scalars().all()

        old_cogs = Decimal("0")
        new_cogs = Decimal("0")

        # 4. Chronological Replay
        for movement in movements:
            # A. Find existing consumptions for this movement
            consumptions_stmt = select(CostConsumption).where(
                CostConsumption.movement_id == movement.id
            )
            existing_consumptions = (await session.execute(consumptions_stmt)).scalars().all()

            # B. Calculate net consumption per layer to safely undo it
            net_consumptions = {}
            original_ids = {}
            layer_costs = {}

            for c in existing_consumptions:
                net_consumptions[c.layer_id] = (
                    net_consumptions.get(c.layer_id, Decimal("0")) + c.qty_consumed
                )
                if c.adjustment_of_id is None:
                    original_ids[c.layer_id] = c.id
                    layer_costs[c.layer_id] = c.unit_cost_at_consumption

            # C. Undo consumption using append-only negation rows
            for layer_id, net_qty in net_consumptions.items():
                if net_qty > 0:
                    unit_cost = layer_costs.get(layer_id, Decimal("0"))
                    old_cogs += net_qty * unit_cost

                    # Restore qty to the layer
                    layer = (
                        await session.execute(select(CostLayer).where(CostLayer.id == layer_id))
                    ).scalar_one()
                    layer.qty_remaining += net_qty

                    # Insert negation row
                    reversal = CostConsumption(
                        layer_id=layer_id,
                        movement_id=movement.id,
                        qty_consumed=-net_qty,
                        unit_cost_at_consumption=unit_cost,
                        adjustment_of_id=original_ids.get(layer_id),
                        adjustment_reason="FR-332 Backdated Recalculation",
                    )
                    session.add(reversal)

            # D. Re-apply consumption strictly chronologically against open layers
            open_layers_stmt = (
                select(CostLayer)
                .where(
                    CostLayer.item_id == item_id,
                    CostLayer.variant_id == variant_id,
                    CostLayer.warehouse_id == warehouse_id,
                    CostLayer.qty_remaining > 0,
                    CostLayer.received_at <= movement.occurred_at,
                )
                .order_by(CostLayer.received_at.asc(), CostLayer.sequence_no.asc())
            )
            open_layers = list((await session.execute(open_layers_stmt)).scalars().all())

            # E. Distribute movement quantity over currently open layers
            quantity_to_consume = abs(movement.qty)
            new_consumptions = _apply_consumption(
                session=session,
                item=item,
                quantity_to_consume=quantity_to_consume,
                movement=movement,
                open_layers=open_layers,
            )

            for nc in new_consumptions:
                new_cogs += nc.qty_consumed * nc.unit_cost_at_consumption

        # 5. COGS True-Up via Transactional Outbox
        cogs_delta = new_cogs - old_cogs
        if cogs_delta != 0:
            logger.info(f"COGS variance detected: {cogs_delta}. Emitting Outbox event.")
            event = CogsVarianceAdjustedEvent(
                tenant_id=tenant_id,
                item_id=item_id,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                delta_amount=cogs_delta,
                reason="FR-332 Backdated Recalculation",
            )
            event_bus = get_event_bus()
            await event_bus.publish(event)

        await session.commit()
