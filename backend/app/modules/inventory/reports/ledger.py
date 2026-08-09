from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.reports.decorators import reporting_tool
from app.modules.inventory.models import CostConsumption, CostLayer, StockMovement


@reporting_tool(
    name="Costed Stock Ledger",
    description_ar="دفتر أستاذ المخزون المقيم",
    required_permission="inventory.reports.ledger.view",
)
async def costed_stock_ledger(
    session: AsyncSession,
    item_id: UUID,
    warehouse_id: UUID,
    variant_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """
    Costed Stock Ledger Report (FR-327).
    Returns every movement for a given item/warehouse with qty, unit_cost,
    extended_cost, and running balances.
    """
    movements_stmt = (
        select(StockMovement)
        .where(
            StockMovement.item_id == item_id,
            StockMovement.warehouse_id == warehouse_id,
            StockMovement.variant_id == variant_id,
        )
        .order_by(StockMovement.occurred_at.asc())
    )
    movements = (await session.execute(movements_stmt)).scalars().all()

    report = []
    running_qty = Decimal("0")
    running_value = Decimal("0")

    for movement in movements:
        if movement.movement_type == "IN":
            # For IN movements, find the exact CostLayer created at the same time
            layer_stmt = select(CostLayer).where(
                CostLayer.item_id == item_id,
                CostLayer.warehouse_id == warehouse_id,
                CostLayer.variant_id == variant_id,
                CostLayer.received_at == movement.occurred_at,
                CostLayer.qty_received == movement.qty,
            ).order_by(CostLayer.sequence_no.desc()).limit(1)
            layer = (await session.execute(layer_stmt)).scalar_one_or_none()

            unit_cost = layer.unit_cost_current if layer else Decimal("0")
            extended_cost = movement.qty * unit_cost
        elif movement.movement_type == "OUT":
            # For OUT movements, calculate the weighted cost based on consumptions
            consumptions_stmt = select(CostConsumption).where(
                CostConsumption.movement_id == movement.id
            )
            consumptions = (await session.execute(consumptions_stmt)).scalars().all()

            total_qty_consumed = sum(c.qty_consumed for c in consumptions)
            total_extended_cost = sum(c.qty_consumed * c.unit_cost_at_consumption for c in consumptions)
            
            unit_cost = (
                (total_extended_cost / total_qty_consumed)
                if total_qty_consumed != 0 else Decimal("0")
            )
            # movement.qty is already negative for OUT movements
            extended_cost = -total_extended_cost 
        else:
            # ADJUST type or unknown
            unit_cost = Decimal("0")
            extended_cost = Decimal("0")

        running_qty += movement.qty
        running_value += extended_cost

        report.append({
            "date": movement.occurred_at,
            "movement_type": movement.movement_type,
            "reference": movement.reference_id,
            "qty": movement.qty,
            "unit_cost": unit_cost,
            "extended_cost": extended_cost,
            "running_qty": running_qty,
            "running_value": running_value,
        })

    return report
