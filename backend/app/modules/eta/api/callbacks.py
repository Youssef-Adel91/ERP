"""
app.modules.eta.api.callbacks — ETA Asynchronous Webhook Callbacks API (Phase 5 - Step 4)

Implements:
  PUT /notifications/documents (FR-550): Receives ETA validation results webhook.
  Fast Return (FR-552): Idempotently reads payload, publishes 'eta.document_status_received'
  domain event via the EventBus, and returns 202 Accepted immediately without blocking.

SECURITY NOTE (fixed — was previously broken in two ways):
  1. This route was never added to TenantMiddleware's bypass list, so ETA's
     unauthenticated callback (it sends no Bearer token or X-Tenant-ID —
     there IS no tenant context yet from ETA's side) was rejected with 401
     before ever reaching this handler. The route was unreachable.
  2. Even if reached, the old code trusted an `x-tenant-id` header or
     `payload["tenantId"]` completely unverified — anyone who could POST to
     this URL could inject a fake status event tagged with ANY tenant_id,
     including one they don't own (e.g. to falsely mark another tenant's
     invoice as REJECTED, or spoof ACCEPTED to bypass compliance checks).

  Fixed by resolving the owning tenant server-side instead of trusting the
  request: the payload's submission/document identifier is looked up
  against each tenant's own EtaSubmission/EtaDocument rows (the same
  identifiers this app itself generated when submitting to ETA — see
  services/gateway.py), and the event is tagged with whichever tenant
  actually owns that identifier. If no match is found anywhere, the
  callback is rejected outright rather than accepted with a guessed tenant.
  This mirrors the resolve-then-verify pattern already used for the
  WhatsApp and Paymob webhooks (app.plugins.whatsapp.api.webhooks,
  app.modules.billing.api_webhooks).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.db.database import public_session, tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.eta.models.core import EtaDocument, EtaSubmission
from app.modules.system.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["eta-callbacks"])


class EtaDocumentStatusReceivedEvent(DomainEvent):
    """
    Domain event published when ETA callback webhook delivers document status (FR-550, FR-552).
    """
    event_type: str = "eta.document_status_received"


async def _resolve_owning_tenant(payload: dict[str, Any]) -> str | None:
    """
    Finds which tenant a callback payload actually belongs to by matching
    its submission/document identifier against real rows — never trusts a
    client-supplied tenant hint. Returns the tenant_id (str) or None if no
    tenant owns this identifier.
    """
    submission_uuid = payload.get("submissionId") or payload.get("submissionUUID")
    document_uuid = payload.get("uuid") or payload.get("documentUuid") or payload.get("documentUUID")
    if not submission_uuid and not document_uuid:
        return None

    async with public_session() as session:
        result = await session.execute(select(Tenant.id))
        tenant_ids = [str(row[0]) for row in result.all()]

    for tenant_id in tenant_ids:
        try:
            async with tenant_session(tenant_id) as session:
                if submission_uuid:
                    hit = await session.execute(
                        select(EtaSubmission.id).where(EtaSubmission.submission_uuid == submission_uuid)
                    )
                    if hit.scalar_one_or_none():
                        return tenant_id
                if document_uuid:
                    hit = await session.execute(
                        select(EtaDocument.id).where(EtaDocument.uuid == document_uuid)
                    )
                    if hit.scalar_one_or_none():
                        return tenant_id
        except Exception:
            # A single tenant's schema being unreachable shouldn't abort
            # the search across the rest — log and keep scanning.
            logger.exception("ETA callback tenant resolution: error scanning tenant=%s", tenant_id)
            continue

    return None


@router.put(
    "/documents",
    status_code=status.HTTP_202_ACCEPTED,
    summary="ETA Asynchronous Document Status Webhook (FR-550, FR-552)",
)
async def eta_document_status_callback(request: Request) -> dict[str, str]:
    """
    Callback endpoint invoked by Egyptian Tax Authority when asynchronous validation completes (FR-550).

    Fast Return (FR-552):
      - Idempotent and non-blocking.
      - Instantly publishes an `eta.document_status_received` domain event via the EventBus outbox.
      - Immediately returns HTTP 202 Accepted so ETA does not retry or drop the connection.
    """
    payload: dict[str, Any] = await request.json()

    tenant_id = await _resolve_owning_tenant(payload)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No submission or document matching this callback was found for any tenant.",
        )

    event = EtaDocumentStatusReceivedEvent(
        tenant_id=tenant_id,
        payload=payload,
    )

    event_bus = get_event_bus()
    async with public_session() as session:
        await event_bus.publish(event, session=session)

    return {
        "status": "ACCEPTED",
        "message": "ETA callback notification queued for asynchronous processing (FR-552).",
    }
