"""
app.modules.logistics.api.webhooks — Carrier Webhooks API Endpoint (FR-752)

Implements:
  POST /api/v1/webhooks/carriers/{carrier_code}
  - Resolves the owning tenant, verifies signature using that tenant's
    REAL carrier webhook secret, checks idempotency dedupe_key, emits
    Outbox event, and returns HTTP 202 Accepted.

Tenant resolution & auth — same category of problem as the WhatsApp
webhook (app.plugins.whatsapp.api.webhooks), and fixed the same way:
Bosta/Mylerz call one fixed URL per carrier with no JWT, so
TenantMiddleware must bypass this path entirely (see its
_BYPASS_PREFIXES in app.core.db.database) and `get_tenant_db` cannot be
used here — it requires request.state.tenant_id to already be set, which
is exactly what bypassed requests don't have.

This previously meant two real bugs, not one:
  1. TenantMiddleware had no bypass entry for this path at all, so every
     inbound carrier webhook was rejected with 401 before reaching this
     handler — the route was unreachable in practice.
  2. Even reaching the handler, the tenant_id was taken unverified from
     an `X-Tenant-ID` header or the payload body, and signature
     verification was called with a hardcoded secret="" — which every
     CarrierProvider.verify_webhook_signature() implementation treats as
     "no secret configured, allow" (see app.modules.logistics.providers.
     bosta.BostaProvider.verify_webhook_signature). That combination let
     ANY caller claim ANY tenant_id and inject fake shipment events into
     that tenant's schema with no cryptographic check at all.

Fixed here by resolving the tenant's OWN CarrierAccount for the given
carrier_code first (from the claimed tenant_id — still just a claim at
this point), fetching that account's real webhook_secret_ref via Vault,
and ONLY THEN calling ingest_carrier_webhook with the real secret. An
attacker who doesn't know a tenant's actual carrier secret can no longer
get a webhook accepted for that tenant, regardless of what tenant_id they
claim in the header — this mirrors how Stripe-style multi-tenant webhook
endpoints resolve the account before trusting anything else about the
request.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.db.database import tenant_session
from app.modules.logistics.models.carriers import CarrierAccount
from app.modules.logistics.services.vault import resolve_webhook_secret
from app.modules.logistics.services.webhooks import ingest_carrier_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/carriers", tags=["Carrier Webhooks"])


@router.post(
    "/{carrier_code}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest Carrier Status Webhook (FR-752, FR-760)",
)
async def receive_carrier_webhook(
    carrier_code: str,
    request: Request,
) -> dict[str, Any]:
    """
    Inbound webhook ingestion endpoint for logistics carriers (Bosta, Mylerz).

    Features:
      1. Tenant resolution from the claimed tenant_id, followed by a real
         cryptographic signature check against THAT tenant's own carrier
         secret (never a hardcoded/empty one).
      2. Deterministic deduplication via CarrierWebhookEvent table (FR-752).
      3. Immediate HTTP 202 Accepted response without blocking.
      4. Emits `logistics.webhook_received` Outbox domain event for async processing (FR-760).
    """
    raw_bytes = await request.body()

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    headers = {k.lower(): v for k, v in request.headers.items()}
    tenant_id_claim = (
        headers.get("x-tenant-id")
        or payload.get("tenant_id")
        or payload.get("tenantId")
    )
    if not tenant_id_claim:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant identification (X-Tenant-ID header or tenant_id in payload).",
        )
    try:
        tenant_uuid = UUID(str(tenant_id_claim))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed tenant identifier.")

    async with tenant_session(tenant_uuid) as session:
        result = await session.execute(
            select(CarrierAccount).where(
                CarrierAccount.carrier_code == carrier_code.lower().strip(),
                CarrierAccount.is_active == True,  # noqa: E712
            )
        )
        account = result.scalar_one_or_none()
        if not account:
            # Deliberately generic — do not reveal whether the tenant
            # exists or just doesn't have this carrier configured.
            logger.warning(
                "Carrier webhook rejected: no active CarrierAccount for carrier='%s' tenant='%s'",
                carrier_code, tenant_id_claim,
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carrier account not found.")

        try:
            secret = resolve_webhook_secret(account.webhook_secret_ref)
        except ValueError as e:
            logger.error("Carrier webhook secret resolution failed for tenant='%s': %s", tenant_id_claim, e)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Carrier account misconfigured.")

        try:
            result = await ingest_carrier_webhook(
                session=session,
                tenant_id=str(tenant_uuid),
                carrier_code=carrier_code,
                payload=payload,
                headers=headers,
                raw_bytes=raw_bytes,
                secret=secret,
            )
            return result
        except ValueError as exc:
            logger.warning("Webhook rejection for carrier='%s': %s", carrier_code, exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
