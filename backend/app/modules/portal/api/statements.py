"""
app/modules/portal/api/statements.py — Client Portal Statements & Payments

Tenant isolation: `/api/v1/portal/*` is a bypass path for TenantMiddleware
(see app.core.db.database._BYPASS_PREFIXES — the portal manages its own
auth, so request.state.tenant_id is never set for these requests), so
these endpoints cannot use the standard `Depends(get_tenant_db)` — that
dependency reads request.state.tenant_id and would always raise 401 here.
Instead, like app.modules.portal.api.auth, each endpoint opens its own
tenant_session(portal_user.tenant_id) using the tenant_id carried in the
OTP-verified portal token (see get_portal_contact).
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.db.database import tenant_session
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.portal.api.auth import get_portal_contact, PortalContactData
from app.modules.portal.services.payments import generate_payment_intent

router = APIRouter(prefix="/portal/invoices", tags=["Portal Statements"])

@router.get("")
async def get_client_invoices(
    portal_user: PortalContactData = Depends(get_portal_contact),
):
    """
    Fetches only finalized (POSTED) and unpaid invoices associated with the authenticated contact_id.
    Strictly isolated to prevent data leaks.
    """
    async with tenant_session(portal_user.tenant_id) as session:
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
):
    """
    Generates a payment intent checkout URL for a specific invoice.
    Enforces that the invoice belongs to the authenticated contact.
    """
    async with tenant_session(portal_user.tenant_id) as session:
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
