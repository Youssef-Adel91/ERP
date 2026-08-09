"""
app/core/notifications/dispatch.py — Multi-Channel Notification Dispatch

Tries WhatsApp first (the primary channel for Egyptian merchants' customers
— see app.plugins.whatsapp.client), and falls back to email when WhatsApp
either isn't configured for the tenant or the send itself fails. Before
this existed, a WhatsApp failure was a silent dead end: the customer never
found out their invoice was posted or that a payment was overdue, and
nothing in the system noticed or tried anything else.

This intentionally does NOT add SMS — no SMS gateway credentials/service
exist anywhere in this codebase's config (unlike WhatsApp and Paymob,
which have real integrations), and stubbing one out with fake behavior
would be worse than not having it. Email was chosen as the fallback
because it needs no third-party account per tenant (only one shared SMTP
config) and every business contact realistically has an email address on
file even when a phone number entered is wrong or unreachable on WhatsApp.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.email import send_email
from app.modules.contacts.models import Contact
from app.plugins.whatsapp.client import whatsapp_client

logger = logging.getLogger(__name__)


async def notify_contact(
    *,
    public_session: AsyncSession,
    tenant_id: UUID | str,
    contact: Contact,
    whatsapp_template: str,
    whatsapp_parameters: list[dict[str, Any]],
    email_subject: str,
    email_body_text: str,
    email_body_html: str | None = None,
) -> str:
    """
    Attempts WhatsApp, falls back to email on any failure/absence of
    config. Returns which channel actually delivered ("whatsapp", "email",
    or "none" if both are unavailable/failed) — callers may log or ignore
    this, it's informational, not a contract any caller currently depends on.
    """
    phone = contact.phone_e164 or contact.phone
    if phone:
        result = await whatsapp_client.send_template_message(
            session=public_session,
            tenant_id=tenant_id,
            phone_number=phone,
            template_name=whatsapp_template,
            parameters=whatsapp_parameters,
        )
        if result is not None:
            return "whatsapp"
        logger.info(
            "WhatsApp delivery unavailable/failed for contact=%s tenant=%s — falling back to email.",
            contact.id, tenant_id,
        )
    else:
        logger.info(
            "No phone number on contact=%s tenant=%s — skipping WhatsApp, trying email.",
            contact.id, tenant_id,
        )

    if contact.email:
        sent = await send_email(
            to_email=contact.email,
            subject=email_subject,
            body_text=email_body_text,
            body_html=email_body_html,
        )
        if sent:
            return "email"

    logger.warning(
        "Notification undeliverable via any channel for contact=%s tenant=%s (no working phone/email or both channels failed).",
        contact.id, tenant_id,
    )
    return "none"
