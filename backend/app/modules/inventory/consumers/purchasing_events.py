"""
app/modules/inventory/consumers/purchasing_events.py — Purchasing Event Consumers

Listens for:
  - purchase.goods_received:
      1. Physically increments stock in StockLevel.
      2. Creates audit trail in StockMovement.
      3. Creates new CostLayer using Base Currency unit cost provided in payload.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.inventory.models.core import CostLayer, StockLevel, StockMovement

logger = logging.getLogger(__name__)
event_bus = get_event_bus()


async def process_goods_received(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> list[CostLayer]:
    """
    Processes 'purchase.goods_received' domain event:
      - Checks idempotency by querying existing StockMovement with reference_id == grn_id.
      - Increments physical stock in StockLevel.
      - Records StockMovement of type 'PURCHASE_RECEIPT'.
      - Creates CostLayer with Base Currency unit cost.
    """
    grn_id = UUID(str(payload["grn_id"]))
    warehouse_id = UUID(str(payload["warehouse_id"]))

    # 1. Idempotency check
    idemp_stmt = select(StockMovement).where(
        StockMovement.reference_id == str(grn_id),
        StockMovement.movement_type == "PURCHASE_RECEIPT",
    )
    res = await session.execute(idemp_stmt)
    if res.scalars().first() is not None:
        logger.warning(
            "⚠️ purchase.goods_received event_id=%s (grn_id=%s) already processed — skipping (idempotent).",
            event_id,
            grn_id,
        )
        return []

    created_layers: list[CostLayer] = []

    for line in payload.get("lines", []):
        item_id = UUID(str(line["item_id"]))
        variant_id = UUID(str(line["variant_id"])) if line.get("variant_id") else None
        batch_id = UUID(str(line["batch_id"])) if line.get("batch_id") else None

        qty_received = Decimal(str(line["qty_received"]))
        unit_cost_base = Decimal(str(line["unit_cost_base"]))

        if qty_received <= 0:
            continue

        # 2. Update or create StockLevel
        level_stmt = (
            select(StockLevel)
            .where(
                StockLevel.item_id == item_id,
                StockLevel.warehouse_id == warehouse_id,
                StockLevel.variant_id == variant_id,
                StockLevel.batch_id == batch_id,
            )
            .with_for_update()
        )
        level_res = await session.execute(level_stmt)
        stock_level = level_res.scalar_one_or_none()

        if not stock_level:
            stock_level = StockLevel(
                item_id=item_id,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                batch_id=batch_id,
                quantity=qty_received,
                qty_reserved=Decimal("0.0000"),
            )
        else:
            stock_level.quantity += qty_received
        session.add(stock_level)

        # 3. Create StockMovement audit trail
        movement = StockMovement(
            item_id=item_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            batch_id=batch_id,
            qty=qty_received,
            movement_type="PURCHASE_RECEIPT",
            reference_id=str(grn_id),
        )
        session.add(movement)

        # 4. Create CostLayer in Base Currency (FR-520)
        cost_layer = CostLayer(
            item_id=item_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            batch_id=batch_id,
            qty_received=qty_received,
            qty_remaining=qty_received,
            unit_cost_original=unit_cost_base,
            unit_cost_current=unit_cost_base,
        )
        session.add(cost_layer)
        created_layers.append(cost_layer)

    await session.flush()
    logger.info(
        "✅ Processed purchase.goods_received (grn_id=%s): Created %d CostLayers in warehouse=%s",
        grn_id,
        len(created_layers),
        warehouse_id,
    )
    return created_layers


@event_bus.subscribe("purchase.goods_received")
async def handle_goods_received(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> list[CostLayer]:
    """EventBus subscriber for 'purchase.goods_received'."""
    if session is not None:
        return await process_goods_received(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_goods_received(sess, event.payload, str(event.event_id))
