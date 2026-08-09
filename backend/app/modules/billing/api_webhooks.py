"""
app.modules.billing.api_webhooks — Paymob Transaction Webhook Receiver

Paymob calls ONE fixed URL (configured in their merchant dashboard, not
per-tenant) with no Bearer token and no X-Tenant-ID — same bare-root,
bypass-path pattern as app.plugins.whatsapp.api.webhooks and
app.modules.logistics.api.webhooks. The tenant is resolved AFTER the
fact, by walking PaymentAttempt.transaction_ref (the Paymob order_id we
stored when initiating checkout in api.start_checkout) -> its
SubscriptionInvoice -> its Subscription -> tenant_id. Authenticity is
verified via Paymob's documented HMAC-SHA512 over the transaction fields
(services.gateway.verify_webhook_hmac) — a request without a valid hmac
is rejected before anything is written.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.db.database import public_session
from app.modules.billing.models.core import (
    PaymentAttempt,
    PaymentStatus,
    Subscription,
    SubscriptionInvoice,
)
from app.modules.billing.services.gateway import verify_webhook_hmac
from app.modules.billing.services.payments import apply_payment_outcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/billing", tags=["Billing Webhook"])


@router.post("/paymob")
async def paymob_webhook(request: Request):
    body = await request.json()
    received_hmac = request.query_params.get("hmac", "")

    if body.get("type") != "TRANSACTION":
        # Paymob also sends other callback types (e.g. token/card); nothing
        # to do with those here.
        return {"status": "ignored"}

    obj = body.get("obj", {})
    if not verify_webhook_hmac(obj, received_hmac):
        logger.warning("Paymob webhook rejected: invalid or missing HMAC")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    order_id = str((obj.get("order") or {}).get("id", ""))
    success = bool(obj.get("success"))
    transaction_id = str(obj.get("id", ""))

    if not order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing order id")

    async with public_session() as session:
        attempt_result = await session.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.transaction_ref == order_id)
            .order_by(PaymentAttempt.created_at.desc())
        )
        pending_attempt = attempt_result.scalars().first()
        if not pending_attempt:
            logger.warning("Paymob webhook: no PaymentAttempt found for order_id=%s", order_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown order")

        invoice = await session.get(SubscriptionInvoice, pending_attempt.invoice_id)
        if not invoice:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

        subscription = await session.get(Subscription, invoice.subscription_id)
        if not subscription:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

        await apply_payment_outcome(
            session,
            invoice=invoice,
            tenant_id=subscription.tenant_id,
            provider="paymob",
            payment_status=PaymentStatus.SUCCEEDED if success else PaymentStatus.FAILED,
            transaction_ref=transaction_id or order_id,
            error_message=None if success else str(obj.get("data", {}).get("message", "Payment failed")),
        )

    return {"status": "ok"}
