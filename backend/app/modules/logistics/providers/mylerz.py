"""
app.modules.logistics.providers.mylerz — Mylerz Shipping Carrier Integration (FR-750, FR-753)

Implements CarrierProvider for Mylerz:
  1. Maps Mylerz raw delivery states to canonical ShipmentState enum (FR-753).
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

# FR-753: Canonical mapping table from Mylerz raw status values to ShipmentState
MYLERZ_STATUS_MAP: dict[str, ShipmentState] = {
    "REGISTERED": ShipmentState.CREATED,
    "CREATED": ShipmentState.CREATED,
    "PICKEDUP": ShipmentState.PICKED_UP,
    "COLLECTED": ShipmentState.PICKED_UP,
    "INTRANSIT": ShipmentState.IN_TRANSIT,
    "SORTING": ShipmentState.IN_TRANSIT,
    "ATWAREHOUSE": ShipmentState.IN_TRANSIT,
    "OUTFORDELIVERY": ShipmentState.OUT_FOR_DELIVERY,
    "OUTPORDELIVERY": ShipmentState.OUT_FOR_DELIVERY,
    "WITHCOURIER": ShipmentState.OUT_FOR_DELIVERY,
    "DELIVERED": ShipmentState.DELIVERED,
    "COMPLETED": ShipmentState.DELIVERED,
    "RETURNING": ShipmentState.RETURNING,
    "RETURNINGTOSENDER": ShipmentState.RETURNING,
    "RETURNED": ShipmentState.RETURNED,
    "RETURNEDTOSENDER": ShipmentState.RETURNED,
    "LOST": ShipmentState.LOST,
    "DAMAGED": ShipmentState.LOST,
    "CANCELLED": ShipmentState.CANCELLED,
    "FAILED": ShipmentState.CANCELLED,
    "REJECTED": ShipmentState.CANCELLED,
}


class MylerzProvider(CarrierProvider):
    """
    Mylerz carrier provider implementation.
    """

    carrier_code: str = "mylerz"

    async def create_shipment(
        self,
        shipment: Shipment,
        invoice_data: dict[str, Any],
        account: CarrierAccount,
    ) -> ShipmentCreationResult:
        """
        Create a new shipment/barcode with Mylerz API.
        Generates a mock Mylerz Barcode and tracking URL.
        """
        barcode = shipment.awb_number or f"MYL-{uuid4().hex[:8].upper()}"
        tracking_url = f"https://www.mylerz.com/tracking/{barcode}"
        logger.info("MylerzProvider: Created shipment Barcode=%s for invoice=%s", barcode, shipment.invoice_id)
        return ShipmentCreationResult(
            awb_number=barcode,
            tracking_url=tracking_url,
            carrier_code=self.carrier_code,
            raw_response={
                "Barcode": barcode,
                "Status": "Registered",
                "CreatedDate": datetime.now(UTC).isoformat(),
            },
        )

    async def cancel_shipment(
        self,
        awb_number: str,
        account: CarrierAccount,
    ) -> bool:
        """Cancel shipment with Mylerz API."""
        logger.info("MylerzProvider: Cancelled shipment Barcode=%s", awb_number)
        return True

    def parse_webhook_payload(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> WebhookParseResult:
        """
        Parse raw Mylerz webhook payload into WebhookParseResult.
        """
        awb_number = (
            payload.get("Barcode")
            or payload.get("barcode")
            or payload.get("AWB")
            or payload.get("awb_number")
            or ""
        )
        status_raw = str(
            payload.get("PackageStatus")
            or payload.get("status")
            or payload.get("Status")
            or "Registered",
        )
        status_normalized = status_raw.upper().replace(" ", "").replace("_", "").strip()
        canonical = MYLERZ_STATUS_MAP.get(status_normalized, ShipmentState.CREATED)

        event_id = str(payload.get("EventId") or payload.get("eventId") or payload.get("_id") or "")
        event_date_str = str(
            payload.get("EventDate") or payload.get("eventDate") or payload.get("timestamp") or "",
        )
        if event_id:
            dedupe_key = f"mylerz:{event_id}"
        else:
            dedupe_key = f"mylerz:{awb_number}:{status_normalized}:{event_date_str or 'default'}"

        event_time = datetime.now(UTC)
        if event_date_str:
            try:
                if event_date_str.replace(".", "", 1).isdigit():
                    ts_val = float(event_date_str)
                    if ts_val > 1000000000000:
                        ts_val /= 1000.0
                    event_time = datetime.fromtimestamp(ts_val, tz=UTC)
                else:
                    event_time = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
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
        Verify Mylerz webhook signature.
        Checks `x-mylerz-signature` header against HMAC-SHA256 hex digest of payload_bytes.
        """
        sig_header = (
            headers.get("x-mylerz-signature")
            or headers.get("x-signature")
            or headers.get("X-Mylerz-Signature", "")
        )
        if not sig_header:
            logger.warning("Mylerz webhook rejected: missing signature header")
            return False
        if not secret:
            logger.warning("Mylerz webhook rejected: no webhook secret configured")
            return False

        computed = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            digestmod="sha256",
        ).hexdigest()
        return hmac.compare_digest(sig_header.lower(), computed.lower())
