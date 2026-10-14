"""
app/modules/sales/services/reminders.py — Overdue Invoice Reminder Engine
"""
from datetime import date
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.core.events.event_bus import get_event_bus, InvoiceOverdueEvent

async def process_overdue_reminders(session: AsyncSession, tenant_id: UUID | str) -> None:
    """
    Scans for unpaid invoices that have passed their due date.
    Publishes an internal domain event (InvoiceOverdueEvent) to the EventBus
    to decouple the sales domain from the notification delivery mechanisms.

    BUG (found via live WhatsApp verification, same family as
    app.modules.sales.services.invoicing.post_invoice's tenant_id bug): this
    used to derive tenant_id per-invoice via
    `str(invoice.tenant_id) if hasattr(invoice, 'tenant_id') ... else "system"`
    — but SalesInvoice is a TenantBase model, and per-tenant tables carry no
    `tenant_id` column at all (tenancy here is schema-per-tenant, not a
    column). `hasattr` was therefore always False, so tenant_id was always
    "system" for every overdue reminder, for every tenant — the same
    "tenant_system doesn't exist" failure mode as the invoice-posted bug.
    Fixed by taking tenant_id as an explicit parameter from the caller
    (which already has it via CurrentUser) instead of guessing from the row.
    """
    today = date.today()
    
    # POSTED invoices represent finalized invoices that have not yet been PAID
    result = await session.execute(
        select(SalesInvoice)
        .where(
            SalesInvoice.status == SalesInvoiceStatus.POSTED,
            SalesInvoice.due_date < today
        )
    )
    overdue_invoices = result.scalars().all()
    
    event_bus = get_event_bus()
    
    tenant_id_str = str(tenant_id)

    for invoice in overdue_invoices:
        event = InvoiceOverdueEvent(
            tenant_id=tenant_id_str,
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "customer_id": str(invoice.contact_id),
                "due_date": invoice.due_date.isoformat(),
                "grand_total": float(invoice.grand_total),
                "currency": invoice.currency,
            }
        )
        # Publish uses the transactional outbox pattern inside the session
        await event_bus.publish(event, session=session)
