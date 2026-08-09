"""
app/modules/sales/services/recurring_worker.py — Background Worker for Recurring Invoices
"""
import uuid
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.models.recurring import RecurringInvoiceProfile, RecurringStatus, RecurringFrequency
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceLine, SalesInvoiceStatus

async def generate_due_recurring_invoices(session: AsyncSession) -> None:
    """
    Scans for active recurring invoice profiles where the next issue date is today or earlier.
    Generates a standard SalesInvoice for each, and schedules the next run date.
    Wrapped in the provided async session transaction.
    """
    today = date.today()
    
    # Select active profiles due for processing and lock them
    result = await session.execute(
        select(RecurringInvoiceProfile)
        .where(
            RecurringInvoiceProfile.status == RecurringStatus.ACTIVE,
            RecurringInvoiceProfile.next_issue_date <= today
        )
        .with_for_update() 
    )
    profiles = result.scalars().all()
    
    for profile in profiles:
        # Check if the profile has reached its end date
        if profile.end_date and profile.next_issue_date > profile.end_date:
            profile.status = RecurringStatus.CANCELLED
            session.add(profile)
            continue
            
        template = profile.invoice_template_data
        
        # Generate a unique invoice number
        invoice_number = template.get("invoice_number_prefix", "REC-") + str(uuid.uuid4())[:8].upper()
        
        # We parse the template data directly into a new SalesInvoice instance
        invoice = SalesInvoice(
            invoice_number=invoice_number,
            order_id=uuid.UUID(template["order_id"]) if "order_id" in template else None,
            contact_id=profile.customer_id,
            status=SalesInvoiceStatus.DRAFT,
            issue_date=today,
            due_date=today + relativedelta(days=template.get("payment_terms_days", 14)),
            currency=template.get("currency", "EGP"),
            subtotal=template.get("subtotal", 0),
            tax_total=template.get("tax_total", 0),
            grand_total=template.get("grand_total", 0),
        )
        
        # Clone line items
        for line_data in template.get("lines", []):
            line = SalesInvoiceLine(
                item_id=uuid.UUID(line_data["item_id"]),
                variant_id=uuid.UUID(line_data["variant_id"]) if line_data.get("variant_id") else None,
                uom_id=uuid.UUID(line_data["uom_id"]) if line_data.get("uom_id") else None,
                qty=line_data["qty"],
                unit_price=line_data["unit_price"],
                line_total=line_data["line_total"],
                tax_rate=line_data.get("tax_rate", 0.14),
                tax_amount=line_data.get("tax_amount", 0),
            )
            invoice.lines.append(line)
            
        session.add(invoice)
        
        # Advance the next issue date mathematically based on the selected frequency
        if profile.frequency == RecurringFrequency.WEEKLY:
            profile.next_issue_date += relativedelta(weeks=1)
        elif profile.frequency == RecurringFrequency.MONTHLY:
            profile.next_issue_date += relativedelta(months=1)
        elif profile.frequency == RecurringFrequency.QUARTERLY:
            profile.next_issue_date += relativedelta(months=3)
        elif profile.frequency == RecurringFrequency.YEARLY:
            profile.next_issue_date += relativedelta(years=1)
            
        session.add(profile)
    
    # We rely on the parent task manager to commit the session
