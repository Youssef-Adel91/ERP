"""
app.modules.billing.services.gateway — Real Payment Gateway Integration (Paymob Accept)

This closes FR-863 (previously open — see api.py's old module docstring):
until now, POST /billing/invoices/{id}/payment-attempts only ever RECORDED
an outcome someone else supplied; nothing in the codebase could actually
initiate a real charge. This module does the real thing against Paymob's
Accept API (the dominant card/wallet gateway for Egyptian merchants):

  1. request_checkout(): the real 3-step Paymob flow —
     a) POST /api/auth/tokens          — short-lived auth token from the API key
     b) POST /api/ecommerce/orders     — register an order for the amount owed
     c) POST /api/acceptance/payment_keys — get a payment token scoped to that order
     Returns an iframe URL the frontend redirects the merchant's card/wallet
     payment to. No money moves in our code — Paymob's hosted iframe handles
     card data; we never touch a raw card number (PCI scope stays with them).

  2. verify_webhook_hmac(): validates Paymob's callback really came from
     Paymob, per their documented HMAC-SHA512 algorithm over a fixed,
     ordered concatenation of transaction fields.

Configuration: PAYMOB_API_KEY / PAYMOB_INTEGRATION_ID / PAYMOB_IFRAME_ID /
PAYMOB_HMAC_SECRET (app.core.config.settings). If any required value for a
given call is missing, this raises PaymentGatewayNotConfiguredError rather
than silently no-op'ing or fabricating a fake success — a merchant must
never see "checkout succeeded" when nothing was actually configured.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentGatewayNotConfiguredError(Exception):
    """Raised when a real charge/verification is attempted without PAYMOB_* configured."""


class PaymentGatewayError(Exception):
    """Raised when Paymob itself rejects a request (bad amount, invalid key, etc.)."""


def _require_configured() -> None:
    missing = [
        name
        for name, value in (
            ("PAYMOB_API_KEY", settings.PAYMOB_API_KEY),
            ("PAYMOB_INTEGRATION_ID", settings.PAYMOB_INTEGRATION_ID),
            ("PAYMOB_IFRAME_ID", settings.PAYMOB_IFRAME_ID),
        )
        if not value
    ]
    if missing:
        raise PaymentGatewayNotConfiguredError(
            "Payment gateway is not configured — missing: " + ", ".join(missing) +
            ". Set these via environment variables before real charges can be initiated."
        )


async def request_checkout(
    *,
    invoice_id: str,
    amount_egp: Decimal,
    merchant_email: str,
    merchant_name: str,
    currency: str = "EGP",
) -> dict[str, Any]:
    """
    Runs the real Paymob 3-step checkout flow and returns:
        {"iframe_url": str, "order_id": int, "payment_key": str}

    amount_egp is in EGP (e.g. Decimal("499.00")); Paymob's API wants the
    amount in the smallest currency unit (piastres), i.e. * 100, as an int.
    """
    _require_configured()

    amount_cents = int((amount_egp * 100).to_integral_value())
    base_url = settings.PAYMOB_BASE_URL.rstrip("/")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Step 1 — Auth token
        auth_resp = await client.post(
            f"{base_url}/api/auth/tokens",
            json={"api_key": settings.PAYMOB_API_KEY},
        )
        if auth_resp.status_code != 201:
            raise PaymentGatewayError(f"Paymob auth failed: {auth_resp.status_code} {auth_resp.text}")
        auth_token = auth_resp.json()["token"]

        # Step 2 — Register order
        order_resp = await client.post(
            f"{base_url}/api/ecommerce/orders",
            json={
                "auth_token": auth_token,
                "delivery_needed": "false",
                "amount_cents": amount_cents,
                "currency": currency,
                "merchant_order_id": invoice_id,
                "items": [],
            },
        )
        if order_resp.status_code not in (200, 201):
            raise PaymentGatewayError(f"Paymob order registration failed: {order_resp.status_code} {order_resp.text}")
        order_id = order_resp.json()["id"]

        # Step 3 — Payment key (scoped to this order + integration)
        name_parts = (merchant_name or "Merchant").strip().split(" ", 1)
        first_name = name_parts[0] or "Merchant"
        last_name = name_parts[1] if len(name_parts) > 1 else "NA"

        key_resp = await client.post(
            f"{base_url}/api/acceptance/payment_keys",
            json={
                "auth_token": auth_token,
                "amount_cents": amount_cents,
                "expiration": 3600,
                "order_id": order_id,
                "billing_data": {
                    "apartment": "NA", "email": merchant_email, "floor": "NA",
                    "first_name": first_name, "street": "NA", "building": "NA",
                    "phone_number": "NA", "shipping_method": "NA", "postal_code": "NA",
                    "city": "Cairo", "country": "EG", "last_name": last_name, "state": "NA",
                },
                "currency": currency,
                "integration_id": int(settings.PAYMOB_INTEGRATION_ID),
            },
        )
        if key_resp.status_code not in (200, 201):
            raise PaymentGatewayError(f"Paymob payment key request failed: {key_resp.status_code} {key_resp.text}")
        payment_key = key_resp.json()["token"]

    iframe_url = f"{base_url}/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
    logger.info("Paymob checkout initiated: order_id=%s invoice_id=%s", order_id, invoice_id)
    return {"iframe_url": iframe_url, "order_id": order_id, "payment_key": payment_key}


# Paymob's documented HMAC field order for the TRANSACTION callback.
# Fields are concatenated as their raw string values (lowercase booleans),
# in this exact order, then HMAC-SHA512'd with PAYMOB_HMAC_SECRET.
_HMAC_FIELD_ORDER = [
    "amount_cents", "created_at", "currency", "error_occured",
    "has_parent_transaction", "id", "integration_id", "is_3d_secure",
    "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
    "is_voided", "order.id", "owner", "pending", "source_data.pan",
    "source_data.sub_type", "source_data.type", "success",
]


def _dig(payload: dict[str, Any], dotted_key: str) -> Any:
    node: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(node, dict):
            return ""
        node = node.get(part, "")
    return node


def verify_webhook_hmac(payload: dict[str, Any], received_hmac: str) -> bool:
    """
    Verifies a Paymob TRANSACTION webhook's `hmac` query param against the
    payload's `obj`, per Paymob's documented concatenation + HMAC-SHA512
    algorithm. Returns False (never raises) on any mismatch or missing
    PAYMOB_HMAC_SECRET — callers must treat False as "reject the webhook".
    """
    if not settings.PAYMOB_HMAC_SECRET or not received_hmac:
        return False

    def _fmt(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return "" if value is None else str(value)

    concatenated = "".join(_fmt(_dig(payload, key)) for key in _HMAC_FIELD_ORDER)
    computed = hmac.new(
        settings.PAYMOB_HMAC_SECRET.encode("utf-8"),
        concatenated.encode("utf-8"),
        digestmod=hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(computed, received_hmac)
