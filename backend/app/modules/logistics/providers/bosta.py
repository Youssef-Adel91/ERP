"""
app.modules.logistics.providers.bosta — Bosta Shipping Carrier Integration (FR-750, FR-753)

Implements CarrierProvider for Bosta:
  1. Maps Bosta raw delivery states to canonical ShipmentState enum (FR-753).
  2. Generates deterministic dedupe_key for webhook replay protection.
  3. Verifies webhook HMAC-SHA256 signature.
"""
from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.modules.logistics.models.carriers import CarrierAccount, Shipment, ShipmentState
from app.modules.logistics.providers.base import (
    CarrierProvider,
    ShipmentCreationResult,
    WebhookParseResult,
)

logger = logging.getLogger(__name__)

# FR-753: Canonical mapping table from Bosta raw status values to ShipmentState
BOSTA_STATUS_MAP: dict[str, ShipmentState] = {
    "TICKET_CREATED": ShipmentState.CREATED,
    "ORDER_CREATED": ShipmentState.CREATED,
    "RECEIVED_AT_WAREHOUSE": ShipmentState.CREATED,
    "PICKED_UP": ShipmentState.PICKED_UP,
    "COLLECTED_FROM_BUSINESS": ShipmentState.PICKED_UP,
    "IN_TRANSIT": ShipmentState.IN_TRANSIT,
    "DISPATCHED": ShipmentState.IN_TRANSIT,
    "ON_HOLD": ShipmentState.IN_TRANSIT,
    "OUT_FOR_DELIVERY": ShipmentState.OUT_FOR_DELIVERY,
    "IN_TRANSIT_TO_RECEIVER": ShipmentState.OUT_FOR_DELIVERY,
    "DELIVERED": ShipmentState.DELIVERED,
    "DELIVERED_TO_RECEIVER": ShipmentState.DELIVERED,
    "RETURNING": ShipmentState.RETURNING,
    "IN_TRANSIT_TO_BUSINESS": ShipmentState.RETURNING,
    "RETURNED": ShipmentState.RETURNED,
    "RETURNED_TO_BUSINESS": ShipmentState.RETURNED,
    "LOST": ShipmentState.LOST,
    "DAMAGED": ShipmentState.LOST,
    "CANCELLED": ShipmentState.CANCELLED,
    "TERMINATED": ShipmentState.CANCELLED,
}


class BostaProvider(CarrierProvider):
    """
    Bosta carrier provider implementation.
    """

    carrier_code: str = "bosta"

    async def create_shipment(
        self,
        shipment: Shipment,
        invoice_data: dict[str, Any],
        account: CarrierAccount,
    ) -> ShipmentCreationResult:
        """
        Create a new shipment/AWB with Bosta API.
        In this implementation we generate a mock AWB and tracking URL.
        """
        awb = shipment.awb_number or f"BST-{uuid4().hex[:8].upper()}"
        tracking_url = f"https://bosta.co/tracking/{awb}"
        logger.info("BostaProvider: Created shipment AWB=%s for invoice=%s", awb, shipment.invoice_id)
        return ShipmentCreationResult(
            awb_number=awb,
            tracking_url=tracking_url,
            carrier_code=self.carrier_code,
            raw_response={
                "_id": uuid4().hex,
                "trackingNumber": awb,
                "state": {"value": "TICKET_CREATED"},
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    async def cancel_shipment(
        self,
        awb_number: str,
        account: CarrierAccount,
    ) -> bool:
        """Cancel shipment with Bosta API."""
        logger.info("BostaProvider: Cancelled shipment AWB=%s", awb_number)
        return True

    def parse_webhook_payload(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> WebhookParseResult:
        """
        Parse raw Bosta webhook payload into WebhookParseResult.
        """
        # Bosta payloads often have {"_id": "...", "trackingNumber": "...", "state": {"value": "DELIVERED"}}
        awb_number = (
            payload.get("trackingNumber")
            or payload.get("awb_number")
            or payload.get("tracking_number")
            or ""
        )
        if not awb_number and "shipment" in payload and isinstance(payload["shipment"], dict):
            awb_number = payload["shipment"].get("trackingNumber", "")

        state_field = payload.get("state")
        if isinstance(state_field, dict):
            status_raw = str(state_field.get("value") or state_field.get("code", "TICKET_CREATED"))
        elif isinstance(state_field, str):
            status_raw = state_field
        else:
            status_raw = str(payload.get("status") or "TICKET_CREATED")

        status_upper = status_raw.upper().strip()
        canonical = BOSTA_STATUS_MAP.get(status_upper, ShipmentState.CREATED)

        event_id = str(payload.get("_id") or payload.get("eventId") or "")
        timestamp_str = str(payload.get("timestamp") or payload.get("eventDate") or "")
        if event_id:
            dedupe_key = f"bosta:{event_id}"
        else:
            dedupe_key = f"bosta:{awb_number}:{status_upper}:{timestamp_str or 'default'}"

        event_time = datetime.now(UTC)
        if timestamp_str:
            try:
                if timestamp_str.replace(".", "", 1).isdigit():
                    ts_val = float(timestamp_str)
                    if ts_val > 1000000000000:  # milliseconds
                        ts_val /= 1000.0
                    event_time = datetime.fromtimestamp(ts_val, tz=UTC)
                else:
                    event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return WebhookParseResult(
            awb_number=awb_number,
            carrier_status_raw=status_raw,
            canonical_state=canonical,
            dedupe_key=dedupe_key,
            event_time=event_time,
            raw_payload=payload,
        )

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        """
        Verify Bosta webhook signature.
        Checks `x-bosta-signature` header against HMAC-SHA256 hex digest of payload_bytes.
        """
        sig_header = (
            headers.get("x-bosta-signature")
            or headers.get("x-signature")
            or headers.get("X-Bosta-Signature", "")
        )
        if not sig_header:
            logger.warning("Bosta webhook rejected: missing signature header")
            return False
        if not secret:
            logger.warning("Bosta webhook rejected: no webhook secret configured")
            return False

        computed = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            digestmod="sha256",
        ).hexdigest()
        return hmac.compare_digest(sig_header.lower(), computed.lower())
