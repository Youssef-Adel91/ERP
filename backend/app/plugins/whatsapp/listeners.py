"""
app/plugins/whatsapp/listeners.py — WhatsApp Event Subscribers
"""
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.db.database import public_session, tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.models.mixins import DocumentState
from app.core.notifications.dispatch import notify_contact
from app.modules.ai.service import answer_question
from app.modules.contacts.models import Contact
from app.plugins.whatsapp.client import whatsapp_client
from app.plugins.whatsapp.models import WhatsAppTenantConfig

logger = logging.getLogger(__name__)
event_bus = get_event_bus()

# Re-pointed from the retired app.plugins.inventory "invoice.created" event
# (published by the now-unmounted app/plugins/inventory router) to the real
# modules/sales event, published by services/invoicing.post_invoice(). That
# payload already carries contact_id/grand_total directly, so this no longer
# needs its own DB round-trip to fetch the invoice row first.
@event_bus.subscribe("sales.invoice_posted")
async def handle_invoice_posted_whatsapp(event: DomainEvent) -> None:
    """
    Listens for posted sales invoices. Notifies the customer via WhatsApp.
    """
    phone = None
    parameters: list[dict] = []

    async with tenant_session(event.tenant_id) as session:
        contact_id_str = event.payload.get("contact_id")
        if not contact_id_str:
            return

        contact = await session.get(Contact, UUID(contact_id_str))
        # Previously gated on having a phone number at all — now also
        # allows contacts with only an email on file, since email can now
        # carry this notification on its own via the fallback channel.
        if not contact or not (contact.phone_e164 or contact.phone or contact.email):
            return

        amount = event.payload.get("grand_total", "0")
        customer_name = contact.name or contact.name_ar or "Customer"

        parameters = [
            {"type": "text", "text": customer_name},
            {"type": "text", "text": str(amount)}
        ]

    # WhatsAppTenantConfig lives in the public schema (see its model
    # docstring), so sending needs its own public-schema session, separate
    # from the tenant-schema session used above for the Contact lookup.
    async with public_session() as public_db:
        await notify_contact(
            public_session=public_db,
            tenant_id=event.tenant_id,
            contact=contact,
            whatsapp_template="new_invoice_created",
            whatsapp_parameters=parameters,
            email_subject="فاتورة جديدة / New Invoice",
            email_body_text=(
                f"مرحبًا {customer_name}،\n\n"
                f"تم إصدار فاتورة جديدة بقيمة {amount}.\n\n"
                f"Hello {customer_name},\n\nA new invoice for {amount} has been issued."
            ),
        )


@event_bus.subscribe("invoice.overdue")
async def handle_invoice_overdue_whatsapp(event: DomainEvent) -> None:
    """
    Listens for overdue invoices from the Recurring worker. Sends a polite Payment Reminder template.
    """
    phone = None
    parameters: list[dict] = []

    async with tenant_session(event.tenant_id) as session:
        customer_id_str = event.payload.get("customer_id")
        if not customer_id_str:
            return

        contact = await session.get(Contact, UUID(customer_id_str))
        if not contact or not (contact.phone_e164 or contact.phone or contact.email):
            return

        total = event.payload.get("grand_total", "0")
        invoice_no = event.payload.get("invoice_number", "")
        customer_name = contact.name or contact.name_ar or "Customer"

        parameters = [
            {"type": "text", "text": customer_name},
            {"type": "text", "text": invoice_no},
            {"type": "text", "text": str(total)}
        ]

    async with public_session() as public_db:
        await notify_contact(
            public_session=public_db,
            tenant_id=event.tenant_id,
            contact=contact,
            whatsapp_template="payment_reminder_ar",
            whatsapp_parameters=parameters,
            email_subject=f"تذكير بالدفع / Payment Reminder — {invoice_no}",
            email_body_text=(
                f"مرحبًا {customer_name}،\n\n"
                f"فاتورتك رقم {invoice_no} بقيمة {total} متأخرة السداد. برجاء السداد في أقرب وقت.\n\n"
                f"Hello {customer_name},\n\nYour invoice {invoice_no} for {total} is overdue. "
                f"Please arrange payment at your earliest convenience."
            ),
        )


def _normalize(number: str | None) -> str:
    """Digits only, no '+' — matches what Meta sends in message.from and
    what tenants are asked to enter in authorized_numbers (see
    WhatsAppConfigIn's docstring)."""
    return "".join(c for c in (number or "") if c.isdigit())


@event_bus.subscribe("whatsapp.message_received")
async def handle_whatsapp_message_ai_bot(event: DomainEvent) -> None:
    """
    Wires the already-live-verified AI Bot (app.modules.ai.service —
    same code POST /api/v1/ai/ask uses) to inbound WhatsApp messages, so
    the tenant can ask it real questions about their own numbers directly
    from WhatsApp — the user's original explicit request.

    SECURITY-CRITICAL gate, added deliberately after a security review
    before this listener existed: a tenant's WhatsApp Business number
    also receives messages from real customers, not just the tenant
    themselves. Without an allowlist check here, any customer texting
    "كام المستحق؟" to the business number would get back the tenant's own
    receivables — a real data leak, not a hypothetical one. So this ONLY
    calls the AI Bot when event.payload["from_number"] (normalized) is in
    that tenant's WhatsAppTenantConfig.authorized_numbers (see that
    field's own docstring). Every other inbound message is left alone —
    silently ignored by this listener (some other listener, e.g. a future
    Case Engine auto-triage, may still act on it; this one just isn't the
    right handler for a message from an unrecognized number).
    """
    from_number = _normalize(event.payload.get("from_number"))
    text = event.payload.get("text_body")
    if not from_number or not text:
        return  # non-text message (image/audio/etc.) — nothing this listener can act on

    async with public_session() as public_db:
        result = await public_db.execute(
            select(WhatsAppTenantConfig).where(WhatsAppTenantConfig.tenant_id == UUID(str(event.tenant_id)))
        )
        config = result.scalar_one_or_none()
        if not config or not config.is_active:
            return

        authorized = {_normalize(n) for n in (config.authorized_numbers or [])}
        if from_number not in authorized:
            logger.info(
                "WhatsApp AI Bot: ignoring message from unauthorized number for tenant %s "
                "(not in authorized_numbers — see WhatsAppTenantConfig docstring)",
                event.tenant_id,
            )
            return

    # Answering needs the TENANT's own schema (reporting functions query
    # tenant tables) — a separate session from the public one used above
    # for the config/allowlist check, same split as every other handler
    # in this file.
    try:
        async with tenant_session(event.tenant_id) as tenant_db:
            answer = await answer_question(tenant_db, text, tenant_id=str(event.tenant_id))
    except Exception as exc:  # noqa: BLE001 — best-effort listener, never crash the webhook handler
        logger.error("WhatsApp AI Bot: answer_question failed for tenant %s: %s", event.tenant_id, exc)
        return

    async with public_session() as public_db:
        await whatsapp_client.send_text_message(
            session=public_db,
            tenant_id=event.tenant_id,
            phone_number=from_number,
            text=answer.answer,
        )


@event_bus.subscribe("ai_draft.approved")
async def handle_ai_draft_approved(event: DomainEvent, session=None) -> None:
    """
    AI Roadmap Level 4 — the actual send. Fires ONLY after a real recorded
    APPROVE decision on an ai_drafted_message (see
    app.modules.approvals.api.decide, which publishes this event using its
    own not-yet-committed session before session.commit()).

    This handler's signature includes `session`, so
    app.core.events.event_bus.EventBus.publish passes that SAME session
    (memory backend, synchronous, same transaction) — the established fix
    for the session-isolation bug class documented in this project's
    lessons learned (a handler opening its own tenant_session here would
    not yet see the just-approved row, since the publisher's transaction
    hasn't committed). The actual WhatsApp send still needs its own
    public-schema session (WhatsAppTenantConfig lives in public), same
    split as every other listener in this file.

    Best-effort by design: never raises. A send failure is recorded on
    draft.send_error (not re-raised), so it never rolls back the already-
    real, already-audited approval decision.
    """
    if session is None:
        logger.error("handle_ai_draft_approved: no session passed by EventBus — cannot proceed.")
        return

    from app.modules.ai.models import AIDraftedMessage  # local import — avoid ai <-> whatsapp import cycle

    draft_id_str = event.payload.get("draft_id")
    if not draft_id_str:
        return

    draft = await session.get(AIDraftedMessage, UUID(draft_id_str))
    if not draft:
        logger.error("handle_ai_draft_approved: draft %s not found.", draft_id_str)
        return

    contact = await session.get(Contact, draft.contact_id)
    phone = contact.phone_e164 or contact.phone if contact else None
    if not phone:
        logger.warning(
            "handle_ai_draft_approved: contact %s has no phone on file — draft %s not sent.",
            draft.contact_id, draft.id,
        )
        draft.send_error = "لا يوجد رقم هاتف مسجل للعميل."
        session.add(draft)
        return

    async with public_session() as public_db:
        result = await whatsapp_client.send_text_message(
            session=public_db,
            tenant_id=event.tenant_id,
            phone_number=phone,
            text=draft.draft_text,
        )

    now = datetime.now(UTC)
    if result is not None:
        draft.sent_at = now
        draft.posted_at = now
        draft.state = DocumentState.POSTED
        draft.send_error = None
    else:
        draft.send_error = "فشل إرسال الرسالة عبر واتساب (راجع سجلات الخادم)."

    session.add(draft)
