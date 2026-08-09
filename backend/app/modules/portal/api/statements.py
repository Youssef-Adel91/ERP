"""
app/modules/portal/api/statements.py — Client Portal Statements & Payments
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db.database import get_tenant_db as get_db_session
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.portal.api.auth import get_portal_contact, PortalContactData
from app.modules.portal.services.payments import generate_payment_intent

router = APIRouter(prefix="/portal/invoices", tags=["Portal Statements"])

@router.get("")
async def get_client_invoices(
    portal_user: PortalContactData = Depends(get_portal_contact),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Fetches only finalized (POSTED) and unpaid invoices associated with the authenticated contact_id.
    Strictly isolated to prevent data leaks.
    """
    result = await session.execute(
        select(SalesInvoice)
        .where(
            SalesInvoice.contact_id == portal_user.contact_id,
            SalesInvoice.status == SalesInvoiceStatus.POSTED
        )
    )
    invoices = result.scalars().all()
    return invoices


@router.post("/{id}/pay")
async def pay_invoice(
    id: UUID,
    portal_user: PortalContactData = Depends(get_portal_contact),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Generates a payment intent checkout URL for a specific invoice.
    Enforces that the invoice belongs to the authenticated contact.
    """
    invoice = await session.get(SalesInvoice, id)
    
    if not invoice or invoice.contact_id != portal_user.contact_id:
        raise HTTPException(status_code=404, detail="Invoice not found or unauthorized.")
        
    if invoice.status != SalesInvoiceStatus.POSTED:
        raise HTTPException(status_code=400, detail="Only POSTED (unpaid) invoices can be paid.")
        
    # Generate mock intent
    intent = await generate_payment_intent(
        invoice_id=invoice.id,
        contact_id=portal_user.contact_id,
        amount=float(invoice.grand_total),
        currency=invoice.currency
    )
    
    return intent
