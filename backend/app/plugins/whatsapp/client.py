"""
app/plugins/whatsapp/client.py — WhatsApp Meta API Client (Tenant-Aware)

Genuinely multi-tenant: every send resolves the CALLING tenant's own
WhatsAppTenantConfig (public schema — see app.plugins.whatsapp.models)
for its phone_number_id and access_token_ref, resolving the latter via
app.plugins.whatsapp.services.vault.resolve_access_token. There is no
global settings.WA_PHONE_NUMBER_ID / settings.WA_ACCESS_TOKEN fallback
anywhere in this file — a tenant with no config, or with is_active=False,
simply gets no message sent (logged, not raised — callers are
best-effort event listeners, not user-facing request/response flows).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.plugins.whatsapp.models import WhatsAppTenantConfig
from app.plugins.whatsapp.services.vault import resolve_access_token

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Stateless — all per-tenant config is resolved fresh on every call."""

    base_url = "https://graph.facebook.com/v17.0"

    async def _get_active_config(
        self, session: AsyncSession, tenant_id: UUID | str
    ) -> WhatsAppTenantConfig | None:
        tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        result = await session.execute(
            select(WhatsAppTenantConfig).where(WhatsAppTenantConfig.tenant_id == tenant_uuid)
        )
        config = result.scalar_one_or_none()
        if not config:
            logger.info("WhatsApp send skipped: tenant %s has no WhatsApp config.", tenant_id)
            return None
        if not config.is_active:
            logger.info("WhatsApp send skipped: tenant %s has WhatsApp integration disabled.", tenant_id)
            return None
        return config

    async def send_template_message(
        self,
        session: AsyncSession,
        tenant_id: UUID | str,
        phone_number: str,
        template_name: str,
        parameters: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Sends a template message via Meta WhatsApp Cloud API using the
        CALLING tenant's own credentials and phone_number_id. `session`
        must be a public-schema session (WhatsAppTenantConfig lives in
        public) — see app.core.db.database.public_session.
        """
        config = await self._get_active_config(session, tenant_id)
        if not config:
            return None

        try:
            access_token = resolve_access_token(config.access_token_ref)
        except ValueError as e:
            logger.error("WhatsApp send aborted for tenant %s: %s", tenant_id, e)
            return None

        url = f"{self.base_url}/{config.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Meta requires phone numbers without the '+' sign
        clean_phone = phone_number.replace("+", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "ar"},
                "components": [
                    {"type": "body", "parameters": parameters}
                ],
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info(
                    "WhatsApp template '%s' sent successfully to %s (tenant %s)",
                    template_name, clean_phone, tenant_id,
                )
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error("WhatsApp API error for %s (tenant %s): %s", clean_phone, tenant_id, e.response.text)
            except httpx.RequestError as e:
                logger.error("WhatsApp network error (tenant %s): %s", tenant_id, str(e))

        return None

    async def send_text_message(
        self,
        session: AsyncSession,
        tenant_id: UUID | str,
        phone_number: str,
        text: str,
    ) -> dict[str, Any] | None:
        """
        Sends a free-form (non-template) text message. Meta only allows
        this within the 24-hour "customer service window" after the user
        last messaged the business — which is exactly the situation this
        is used for (app.plugins.whatsapp.listeners.handle_whatsapp_message_ai_bot
        replying to an inbound message the tenant just sent), so a
        template isn't needed or appropriate here. Same
        config-resolution/error-handling discipline as
        send_template_message above — best-effort, logs and returns None
        on failure rather than raising, since callers are event listeners.
        """
        config = await self._get_active_config(session, tenant_id)
        if not config:
            return None

        try:
            access_token = resolve_access_token(config.access_token_ref)
        except ValueError as e:
            logger.error("WhatsApp send aborted for tenant %s: %s", tenant_id, e)
            return None

        url = f"{self.base_url}/{config.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        clean_phone = phone_number.replace("+", "")

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {"body": text},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info(
                    "WhatsApp text reply sent to %s (tenant %s)", clean_phone, tenant_id,
                )
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error("WhatsApp API error for %s (tenant %s): %s", clean_phone, tenant_id, e.response.text)
            except httpx.RequestError as e:
                logger.error("WhatsApp network error (tenant %s): %s", tenant_id, str(e))

        return None


whatsapp_client = WhatsAppClient()
