"""
app/modules/sales/services/reminders.py — Overdue Invoice Reminder Engine
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.core.events.event_bus import get_event_bus, InvoiceOverdueEvent

async def process_overdue_reminders(session: AsyncSession) -> None:
    """
    Scans for unpaid invoices that have passed their due date.
    Publishes an internal domain event (InvoiceOverdueEvent) to the EventBus
    to decouple the sales domain from the notification delivery mechanisms.
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
    
    for invoice in overdue_invoices:
        # Determine the tenant scope (fallback to "system" if undefined)
        tenant_id_str = str(invoice.tenant_id) if hasattr(invoice, 'tenant_id') and invoice.tenant_id else "system"
        
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
