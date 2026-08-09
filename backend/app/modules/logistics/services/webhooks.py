"""
app.modules.logistics.services.webhooks — Idempotent Webhook Ingestion Service (FR-752)

Implements:
  1. ingest_carrier_webhook(): Verifies signature, checks dedupe_key against CarrierWebhookEvent,
     saves audit log, and publishes CarrierWebhookReceivedEvent to the Outbox for non-blocking processing.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.event_bus import get_event_bus
from app.modules.logistics.models.carriers import CarrierWebhookEvent
from app.modules.logistics.providers.registry import get_carrier_provider

logger = logging.getLogger(__name__)


async def ingest_carrier_webhook(
    session: AsyncSession,
    tenant_id: str,
    carrier_code: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    raw_bytes: bytes,
    secret: str = "",
) -> dict[str, Any]:
    """
    Ingest a carrier webhook with signature verification and replay protection (FR-752).

    Returns a dict with `status` ("accepted" or "ignored") and deduplication details.
    """
    provider = get_carrier_provider(carrier_code)

    # 1. Verify cryptographic signature if secret is configured
    if not provider.verify_webhook_signature(raw_bytes, headers, secret):
        logger.warning(
            "Invalid webhook signature for carrier='%s' (tenant='%s')",
            carrier_code,
            tenant_id,
        )
        raise ValueError("Invalid webhook signature")

    # 2. Parse payload into canonical format and get deterministic dedupe_key
    parsed = provider.parse_webhook_payload(payload, headers)

    # 3. Idempotency & Replay Protection: Check if dedupe_key already ingested
    stmt = select(CarrierWebhookEvent).where(
        CarrierWebhookEvent.dedupe_key == parsed.dedupe_key,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(
            "Idempotent replay: Webhook with dedupe_key='%s' already ingested for carrier='%s'. Ignoring.",
            parsed.dedupe_key,
            carrier_code,
        )
        return {
            "status": "ignored",
            "reason": "duplicate_webhook",
            "dedupe_key": parsed.dedupe_key,
            "awb_number": parsed.awb_number,
        }

    # 4. Save raw webhook event for audit
    webhook_event = CarrierWebhookEvent(
        carrier_code=carrier_code,
        dedupe_key=parsed.dedupe_key,
        payload_json=payload,
        headers_json=headers,
        signature_valid=True,
        received_at=datetime.now(UTC),
    )
    session.add(webhook_event)
    await session.flush()

    # 5. Transactional Outbox: Publish domain event for async background processing
    from app.modules.logistics.events import CarrierWebhookReceivedEvent

    event = CarrierWebhookReceivedEvent(
        tenant_id=tenant_id,
        payload={
            "carrier_code": carrier_code,
            "awb_number": parsed.awb_number,
            "canonical_state": parsed.canonical_state.value,
            "carrier_status_raw": parsed.carrier_status_raw,
            "dedupe_key": parsed.dedupe_key,
            "raw_payload": payload,
        },
    )
    await get_event_bus().publish(event, session=session)

    logger.info(
        "Ingested webhook carrier='%s' AWB='%s' status='%s' dedupe_key='%s'",
        carrier_code,
        parsed.awb_number,
        parsed.canonical_state.value,
        parsed.dedupe_key,
    )

    return {
        "status": "accepted",
        "dedupe_key": parsed.dedupe_key,
        "awb_number": parsed.awb_number,
        "canonical_state": parsed.canonical_state.value,
    }
