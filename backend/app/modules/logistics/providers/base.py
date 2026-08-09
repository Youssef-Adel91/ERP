"""
app.modules.logistics.providers.base — Carrier Provider Interface & DTOs (FR-750, FR-753)

Defines:
  1. ShipmentCreationResult: Standardized output from shipment creation across providers.
  2. WebhookParseResult: Standardized parsed webhook payload with canonical state and dedupe_key.
  3. CarrierProvider: Protocol contract required for all carrier integrations (Bosta, Mylerz, etc.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.modules.logistics.models.carriers import CarrierAccount, Shipment, ShipmentState


class ShipmentCreationResult(BaseModel):
    """Result returned by a carrier provider when a shipment is created."""

    awb_number: str
    tracking_url: str | None = None
    carrier_code: str
    raw_response: dict[str, Any] = Field(default_factory=dict)


class WebhookParseResult(BaseModel):
    """Parsed webhook event data normalized across carriers."""

    awb_number: str
    carrier_status_raw: str
    canonical_state: ShipmentState
    dedupe_key: str
    event_time: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class CarrierProvider(Protocol):
    """
    Protocol definition for carrier providers (FR-750).
    Every carrier implementation must conform to this contract.
    """

    carrier_code: str

    async def create_shipment(
        self,
        shipment: Shipment,
        invoice_data: dict[str, Any],
        account: CarrierAccount,
    ) -> ShipmentCreationResult:
        """Create a new waybill/shipment with the carrier."""
        ...

    async def cancel_shipment(
        self,
        awb_number: str,
        account: CarrierAccount,
    ) -> bool:
        """Cancel an existing waybill/shipment with the carrier."""
        ...

    def parse_webhook_payload(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> WebhookParseResult:
        """
        Parse raw webhook JSON from the carrier into a standardized WebhookParseResult,
        mapping raw carrier statuses to canonical ShipmentState (FR-753) and generating
        a deterministic dedupe_key for replay protection.
        """
        ...

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: dict[str, str],
        secret: str,
    ) -> bool:
        """
        Verify cryptographic signature of the webhook request (e.g. HMAC-SHA256).
        Returns True if signature is valid or if verification succeeds.
        """
        ...
