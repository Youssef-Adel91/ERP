"""
app.modules.billing.services.payments — Shared Payment Outcome Application

Extracted so both the manual admin-facing endpoint
(api.record_payment_attempt) and the real inbound Paymob webhook
(api_webhooks.paymob_webhook) apply a payment result through the exact
same path: create the PaymentAttempt row, mark the invoice PAID on
success, or hand off to the real dunning engine on failure. One place to
get this right instead of two copies drifting apart.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models.core import (
    InvoiceStatus,
    PaymentAttempt,
    PaymentStatus,
    SubscriptionInvoice,
)
from app.modules.billing.services.dunning import process_failed_payment
from app.modules.billing.services.entitlements import invalidate_entitlements


async def apply_payment_outcome(
    session: AsyncSession,
    *,
    invoice: SubscriptionInvoice,
    tenant_id: UUID,
    provider: str,
    payment_status: PaymentStatus,
    transaction_ref: str | None = None,
    error_message: str | None = None,
) -> PaymentAttempt:
    attempt = PaymentAttempt(
        invoice_id=invoice.id,
        provider=provider,
        transaction_ref=transaction_ref,
        status=payment_status,
        error_message=error_message,
    )
    session.add(attempt)

    if payment_status == PaymentStatus.SUCCEEDED:
        invoice.status = InvoiceStatus.PAID
        session.add(invoice)
        await session.commit()
        await invalidate_entitlements(tenant_id)
    elif payment_status == PaymentStatus.FAILED:
        await session.commit()
        await process_failed_payment(session, invoice.id)
    else:
        await session.commit()

    await session.refresh(attempt)
    return attempt
