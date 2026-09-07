"""
app/plugins/whatsapp/listeners.py — WhatsApp Event Subscribers
"""
import logging
from uuid import UUID

from app.core.events.event_bus import get_event_bus, DomainEvent
from app.core.db.database import public_session, tenant_session
from app.core.notifications.dispatch import notify_contact
from app.modules.contacts.models import Contact

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
