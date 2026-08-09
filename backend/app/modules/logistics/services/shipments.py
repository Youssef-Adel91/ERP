"""
app.modules.logistics.services.shipments — Shipment Management & Status Transitions (FR-756, FR-760)

Implements:
  1. create_shipment(): Orchestrates shipment creation via CarrierProvider and emits status event.
  2. update_shipment_status(): Updates canonical shipment state and emits status transition event (FR-760).
  3. FR-756 COMPLIANCE GUARD: Ensures carrier status RETURNED never triggers inventory restock without physical return_received_at.
  4. record_physical_return_receipt(): Records physical warehouse check-in for inventory restock.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.event_bus import get_event_bus
from app.modules.logistics.models.carriers import (
    CarrierAccount,
    Shipment,
    ShipmentEvent,
    ShipmentState,
)
from app.modules.logistics.providers.registry import get_carrier_provider

logger = logging.getLogger(__name__)


async def create_shipment(
    session: AsyncSession,
    tenant_id: str,
    invoice_id: UUID,
    carrier_code: str,
    cod_amount: Decimal,
    invoice_data: dict[str, Any],
    account: CarrierAccount,
) -> Shipment:
    """
    Create a new shipment for an invoice using the specified carrier provider (FR-750).
    Emits `shipment.status_updated` via the Outbox (FR-760).
    """
    provider = get_carrier_provider(carrier_code)

    shipment = Shipment(
        invoice_id=invoice_id,
        carrier_code=carrier_code,
        awb_number="",  # Will be populated by provider
        state=ShipmentState.CREATED,
        cod_amount=cod_amount,
    )

    result = await provider.create_shipment(
        shipment=shipment,
        invoice_data=invoice_data,
        account=account,
    )

    shipment.awb_number = result.awb_number
    shipment.tracking_url = result.tracking_url
    session.add(shipment)
    await session.flush()

    # Record initial shipment event
    event_log = ShipmentEvent(
        shipment_id=shipment.id,
        carrier_code=carrier_code,
        carrier_status_raw="CREATED",
        canonical_state=ShipmentState.CREATED,
        payload_json=result.raw_response,
        event_time=datetime.now(UTC),
    )
    session.add(event_log)

    # FR-760: Emit terminal/state transition status event to EventBus Outbox
    # Note: Using delayed import to prevent circular dependency
    from app.modules.logistics.events import ShipmentStatusUpdatedEvent

    event = ShipmentStatusUpdatedEvent(
        tenant_id=tenant_id,
        payload={
            "shipment_id": str(shipment.id),
            "invoice_id": str(invoice_id),
            "awb_number": shipment.awb_number,
            "carrier_code": carrier_code,
            "old_state": "",
            "new_state": ShipmentState.CREATED.value,
            "cod_amount": str(cod_amount),
            "physical_return_received": False,
        },
    )
    await get_event_bus().publish(event, session=session)

    logger.info(
        "Created shipment id=%s AWB=%s for invoice=%s (carrier=%s)",
        shipment.id,
        shipment.awb_number,
        invoice_id,
        carrier_code,
    )
    return shipment


async def update_shipment_status(
    session: AsyncSession,
    tenant_id: str,
    shipment: Shipment,
    canonical_state: ShipmentState,
    status_raw: str,
    payload: dict[str, Any],
) -> Shipment:
    """
    Update canonical shipment status from a carrier webhook or manual event (FR-753, FR-760).

    # =========================================================================
    # FR-756 COMPLIANCE GUARD — PHYSICAL RETURN RECEIPT vs. CARRIER STATUS
    # =========================================================================
    # When a carrier webhook transitions `shipment.state` to `ShipmentState.RETURNED`,
    # we DO NOT automatically trigger an inventory restock or adjust stock levels.
    #
    # WHY:
    #   1. Carrier status updates are untrusted for physical inventory custody.
    #   2. Packages reported "Returned" by couriers may be damaged, missing items,
    #      or still in transit back to the warehouse.
    #   3. Inventory restock MUST ONLY occur when a warehouse operator physically
    #      inspects and receives the package, setting `shipment.return_received_at`.
    #
    # RULE:
    #   - This method updates `shipment.state` and emits `shipment.status_updated`.
    #   - It intentionally leaves `shipment.return_received_at` unmodified.
    #   - Inventory modules subscribing to `shipment.status_updated` MUST check
    #     `return_received_at` before restoring items to sellable stock.
    # =========================================================================
    """
    old_state = shipment.state

    # Record audit transition in ShipmentEvent table
    event_log = ShipmentEvent(
        shipment_id=shipment.id,
        carrier_code=shipment.carrier_code,
        carrier_status_raw=status_raw,
        canonical_state=canonical_state,
        payload_json=payload,
        event_time=datetime.now(UTC),
    )
    session.add(event_log)

    # Update shipment canonical state
    shipment.state = canonical_state
    session.add(shipment)
    await session.flush()

    # FR-760: Emit status transition event to EventBus Outbox when state changes
    if canonical_state != old_state:
        from app.modules.logistics.events import ShipmentStatusUpdatedEvent

        event = ShipmentStatusUpdatedEvent(
            tenant_id=tenant_id,
            payload={
                "shipment_id": str(shipment.id),
                "invoice_id": str(shipment.invoice_id),
                "awb_number": shipment.awb_number,
                "carrier_code": shipment.carrier_code,
                "old_state": old_state.value,
                "new_state": canonical_state.value,
                "cod_amount": str(shipment.cod_amount),
                "physical_return_received": shipment.return_received_at is not None,
            },
        )
        await get_event_bus().publish(event, session=session)

        logger.info(
            "Shipment AWB=%s status changed: %s -> %s (return_received_at=%s)",
            shipment.awb_number,
            old_state.value,
            canonical_state.value,
            shipment.return_received_at,
        )

    return shipment


async def record_physical_return_receipt(
    session: AsyncSession,
    tenant_id: str,
    shipment_id: UUID,
) -> Shipment:
    """
    FR-756: Record physical receipt of a returned shipment at the warehouse.
    Sets `return_received_at = datetime.now(UTC)` and emits status update so inventory
    can now safely perform physical restock.
    """
    stmt = select(Shipment).where(Shipment.id == shipment_id)
    result = await session.execute(stmt)
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise ValueError(f"Shipment {shipment_id} not found.")

    if shipment.state != ShipmentState.RETURNED:
        raise ValueError(
            f"Cannot record physical return receipt for shipment in state '{shipment.state.value}'. "
            f"Shipment must be in '{ShipmentState.RETURNED.value}' state.",
        )

    now = datetime.now(UTC)
    shipment.return_received_at = now
    session.add(shipment)
    await session.flush()

    from app.modules.logistics.events import ShipmentStatusUpdatedEvent

    event = ShipmentStatusUpdatedEvent(
        tenant_id=tenant_id,
        payload={
            "shipment_id": str(shipment.id),
            "invoice_id": str(shipment.invoice_id),
            "awb_number": shipment.awb_number,
            "carrier_code": shipment.carrier_code,
            "old_state": shipment.state.value,
            "new_state": shipment.state.value,
            "cod_amount": str(shipment.cod_amount),
            "physical_return_received": True,
            "return_received_at": now.isoformat(),
        },
    )
    await get_event_bus().publish(event, session=session)

    logger.info(
        "Recorded physical warehouse return receipt for shipment id=%s AWB=%s",
        shipment.id,
        shipment.awb_number,
    )
    return shipment


async def process_shipment_webhook_payload(
    session: AsyncSession,
    tenant_id: str,
    payload: dict[str, Any],
) -> None:
    """
    Asynchronously process an ingested carrier webhook payload.
    Looks up shipment by AWB number and applies status update.
    """
    awb_number = payload.get("awb_number") or ""
    carrier_code = payload.get("carrier_code") or ""
    canonical_state_str = payload.get("canonical_state") or "created"
    status_raw = payload.get("carrier_status_raw") or canonical_state_str
    raw_payload = payload.get("raw_payload") or payload

    if not awb_number:
        logger.warning("Webhook processing skipped: no AWB number found in payload=%s", payload)
        return

    try:
        canonical_state = ShipmentState(canonical_state_str)
    except ValueError:
        canonical_state = ShipmentState.CREATED

    stmt = select(Shipment).where(Shipment.awb_number == awb_number)
    result = await session.execute(stmt)
    shipment = result.scalar_one_or_none()

    if not shipment:
        logger.warning("Shipment with AWB=%s not found in tenant '%s'.", awb_number, tenant_id)
        return

    await update_shipment_status(
        session=session,
        tenant_id=tenant_id,
        shipment=shipment,
        canonical_state=canonical_state,
        status_raw=status_raw,
        payload=raw_payload,
    )
