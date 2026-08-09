"""
app/plugins/whatsapp/api/webhooks.py — Meta Webhook Receiver (Tenant-Aware)

Meta calls ONE global URL for the entire platform (no tenant_id in the
URL, no auth). Inbound resolution therefore works backwards from the
payload: every entry.changes[].value.metadata.phone_number_id is looked
up against the public WhatsAppTenantConfig table (unique on
phone_number_id — see its model docstring) to find the owning tenant,
and only then is a whatsapp.message_received DomainEvent published with
that resolved tenant context, so downstream listeners (the generic Case
Engine, etc.) get a correctly-scoped event.

hub.verify_token (GET handshake) and the X-Hub-Signature-256 app secret
(POST signature check) both remain app-level (settings.WA_VERIFY_TOKEN /
settings.WA_APP_SECRET), NOT per-tenant, deliberately — these authenticate
the Meta *App* registration and its single global webhook URL, not any
one tenant's WhatsApp Business number. A tenant's own credentials
(phone_number_id, access_token_ref) only come into play for OUTBOUND
sends via WhatsAppClient. This is a real, intentional asymmetry, not an
oversight.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import logging

from fastapi import APIRouter, Request, HTTPException, Response
from sqlalchemy import select

from app.core.config import settings
from app.core.db.database import public_session
from app.core.events.event_bus import get_event_bus, WhatsAppMessageReceivedEvent
from app.plugins.whatsapp.models import WhatsAppTenantConfig

logger = logging.getLogger(__name__)
event_bus = get_event_bus()

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp Webhook"])


@router.get("")
async def verify_webhook(request: Request):
    """
    Meta webhook verification endpoint.
    Meta sends GET request with hub.mode, hub.challenge, and hub.verify_token.
    """
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    verify_token = request.query_params.get("hub.verify_token")

    expected_token = getattr(settings, "WA_VERIFY_TOKEN", "omni_erp_wa_verify")

    if mode == "subscribe" and verify_token == expected_token:
        return Response(content=str(challenge))

    raise HTTPException(status_code=403, detail="Verification failed")


async def _resolve_tenant_id(session, phone_number_id: str) -> str | None:
    """Reverse-lookup: Meta's phone_number_id -> our tenant_id, via the
    public WhatsAppTenantConfig table (unique on phone_number_id)."""
    result = await session.execute(
        select(WhatsAppTenantConfig).where(WhatsAppTenantConfig.phone_number_id == phone_number_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        logger.warning("WhatsApp webhook: no tenant registered for phone_number_id=%s", phone_number_id)
        return None
    return str(config.tenant_id)


@router.post("")
async def receive_webhook(request: Request):
    """
    Receives inbound messages and message status updates (Delivered,
    Read, Failed) from Meta. Validates payload signature using SHA256,
    then resolves each change's phone_number_id to a tenant and publishes
    a whatsapp.message_received event per inbound message found.
    """
    app_secret = getattr(settings, "WA_APP_SECRET", "test_secret")
    signature = request.headers.get("X-Hub-Signature-256", "")

    body = await request.body()

    if signature:
        expected_sig = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("WhatsApp webhook signature mismatch")
            raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logger.warning("WhatsApp webhook: unparseable JSON body")
        return {"status": "ok"}

    entries = payload.get("entry", [])

    async with public_session() as session:
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                if not phone_number_id:
                    continue

                messages = value.get("messages", [])
                if not messages:
                    # Status callbacks (delivered/read/failed) — nothing to
                    # route to a tenant-facing event yet, skip silently.
                    continue

                tenant_id = await _resolve_tenant_id(session, phone_number_id)
                if not tenant_id:
                    continue

                for message in messages:
                    event = WhatsAppMessageReceivedEvent(
                        tenant_id=tenant_id,
                        payload={
                            "phone_number_id": phone_number_id,
                            "from_number": message.get("from"),
                            "wa_message_id": message.get("id"),
                            "message_type": message.get("type"),
                            "text_body": (message.get("text") or {}).get("body"),
                            "raw_message": message,
                        },
                    )
                    await event_bus.publish(event, session=session)

    # Always 200 back to Meta regardless of routing outcome, or it will
    # keep retrying/disable the subscription.
    return {"status": "ok"}
