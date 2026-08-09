"""
app/core/notifications/email.py — Generic SMTP Email Sender

The fallback notification channel: when WhatsApp send fails (network
error, API error, tenant has no WhatsApp config, tenant disabled it), a
customer-facing notification (new invoice, payment reminder) would
previously just silently disappear — logged, but never actually delivered
to the customer by any channel. This gives every such notification a
second real path.

Same discipline as the Paymob gateway stub (app.modules.billing.services.
gateway): refuses to attempt a send when SMTP isn't configured, logging
clearly rather than pretending to succeed or raising and crashing an
event-listener call site that's meant to be best-effort.
"""
from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


async def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> bool:
    """
    Sends a single email via SMTP. Returns True on success, False on any
    failure (never raises) — callers are notification best-effort paths,
    not user-facing request/response flows, matching the WhatsApp client's
    contract (app.plugins.whatsapp.client.WhatsAppClient.send_template_message).
    """
    if not is_configured():
        logger.info("Email send skipped: SMTP not configured (SMTP_HOST/SMTP_FROM_EMAIL unset).")
        return False

    if not to_email or "@" not in to_email:
        logger.warning("Email send skipped: invalid recipient address %r.", to_email)
        return False

    message = EmailMessage()
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_USE_TLS,
            timeout=10.0,
        )
        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception:
        logger.exception("Email send failed for %s", to_email)
        return False
