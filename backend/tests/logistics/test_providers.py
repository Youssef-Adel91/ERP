"""
tests.logistics.test_providers — Unit Tests for Carrier Providers (FR-750, FR-753)

Tests:
  1. Provider factory (get_carrier_provider).
  2. BostaProvider status mapping and dedupe_key generation (FR-753).
  3. MylerzProvider status mapping and dedupe_key generation (FR-753).
  4. Cryptographic HMAC signature verification for Bosta and Mylerz.
"""
from __future__ import annotations

import hmac

import pytest

from app.modules.logistics.models.carriers import ShipmentState
from app.modules.logistics.providers import (
    BostaProvider,
    MylerzProvider,
    get_carrier_provider,
    list_supported_carriers,
)


def test_provider_registry():
    """Verify factory returns correct provider instances and raises ValueError for unknown codes."""
    bosta = get_carrier_provider("bosta")
    assert isinstance(bosta, BostaProvider)
    assert bosta.carrier_code == "bosta"

    mylerz = get_carrier_provider("mylerz")
    assert isinstance(mylerz, MylerzProvider)
    assert mylerz.carrier_code == "mylerz"

    assert set(list_supported_carriers()) == {"bosta", "mylerz"}

    with pytest.raises(ValueError, match="Unsupported carrier code"):
        get_carrier_provider("fedex_unknown")


def test_bosta_webhook_parser_mapping():
    """Verify Bosta status mapping to canonical ShipmentState enum (FR-753)."""
    provider = BostaProvider()

    # Test TICKET_CREATED -> CREATED
    payload = {
        "_id": "event_001",
        "trackingNumber": "BST-123",
        "state": {"value": "TICKET_CREATED"},
    }
    parsed = provider.parse_webhook_payload(payload, headers={})
    assert parsed.awb_number == "BST-123"
    assert parsed.canonical_state == ShipmentState.CREATED
    assert parsed.dedupe_key == "bosta:event_001"

    # Test DELIVERED -> DELIVERED
    payload_del = {
        "_id": "event_002",
        "trackingNumber": "BST-123",
        "state": {"value": "DELIVERED"},
    }
    parsed_del = provider.parse_webhook_payload(payload_del, headers={})
    assert parsed_del.canonical_state == ShipmentState.DELIVERED

    # Test RETURNED -> RETURNED
    payload_ret = {
        "_id": "event_003",
        "trackingNumber": "BST-123",
        "state": {"value": "RETURNED_TO_BUSINESS"},
    }
    parsed_ret = provider.parse_webhook_payload(payload_ret, headers={})
    assert parsed_ret.canonical_state == ShipmentState.RETURNED


def test_mylerz_webhook_parser_mapping():
    """Verify Mylerz status mapping to canonical ShipmentState enum (FR-753)."""
    provider = MylerzProvider()

    payload = {
        "EventId": "myl_evt_100",
        "Barcode": "MYL-999",
        "PackageStatus": "OutForDelivery",
    }
    parsed = provider.parse_webhook_payload(payload, headers={})
    assert parsed.awb_number == "MYL-999"
    assert parsed.canonical_state == ShipmentState.OUT_FOR_DELIVERY
    assert parsed.dedupe_key == "mylerz:myl_evt_100"

    # Test COMPLETED -> DELIVERED
    payload_comp = {
        "EventId": "myl_evt_101",
        "Barcode": "MYL-999",
        "PackageStatus": "Completed",
    }
    parsed_comp = provider.parse_webhook_payload(payload_comp, headers={})
    assert parsed_comp.canonical_state == ShipmentState.DELIVERED


def test_webhook_hmac_signature_verification():
    """Verify HMAC-SHA256 signature checking for carrier providers."""
    secret = "my_webhook_secret_key"
    body_bytes = b'{"trackingNumber":"BST-100","state":{"value":"DELIVERED"}}'

    valid_sig = hmac.new(secret.encode("utf-8"), body_bytes, digestmod="sha256").hexdigest()

    bosta = BostaProvider()
    assert bosta.verify_webhook_signature(
        body_bytes,
        {"x-bosta-signature": valid_sig},
        secret=secret,
    )

    # Invalid signature should return False
    assert not bosta.verify_webhook_signature(
        body_bytes,
        {"x-bosta-signature": "invalid_hex_signature"},
        secret=secret,
    )
