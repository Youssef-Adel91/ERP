"""
app/modules/billing/api.py — Billing & Subscriptions REST API (Phase 8, launch-blocker)

Exposes the Plan/Subscription/SubscriptionInvoice/PaymentAttempt engine
(app.modules.billing.services.*). Plan, Subscription, SubscriptionInvoice and
PaymentAttempt all live in the `public` schema (cross-tenant, one row per
tenant's subscription) — every endpoint uses `get_public_db`, not
`get_tenant_db`.

Scope of this pass (per explicit priority instruction — Billing/Dunning are
launch-blocking per Phase 8):
  - Plan catalogue: list (any authenticated user), seed (OWNER/ADMIN — calls
    the real idempotent services.seed.seed_plans, no fabricated data).
  - Subscription: read the calling tenant's own subscription, create/upgrade
    it (OWNER/ADMIN only — this is a billing-affecting action).
  - Subscription invoices: list/read the calling tenant's own invoices.
  - Checkout: POST /invoices/{id}/checkout now initiates a REAL Paymob
    charge (services.gateway.request_checkout) and returns an iframe_url —
    FR-863 is closed. Requires PAYMOB_API_KEY/INTEGRATION_ID/IFRAME_ID to
    be configured; fails loudly (503) if not, never fakes success.
  - Payment attempts: record an attempt against an invoice. The real Paymob
    webhook (app.modules.billing.api_webhooks, bare-root/bypass path) is
    what normally drives this now; this endpoint still exists for manual
    admin correction. A SUCCEEDED attempt marks the invoice PAID; a FAILED
    attempt invokes the real dunning engine
    (services.dunning.process_failed_payment) which enforces graceful
    degradation to READ_ONLY, never deletes data.
  - Entitlements: read-through check for the calling tenant (Redis-cached,
    services.entitlements.get_tenant_entitlements / check_entitlement).
  - ETA dogfooding: manually trigger submission of a subscription invoice to
    the Egyptian Tax Authority under our own internal system tenant
    (services.invoicing.generate_eta_subscription_invoice) — OWNER/ADMIN
    only, since it's an internal/back-office operation, not a merchant
    self-service action.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.modules.billing.models.core import (
    InvoiceStatus,
    PaymentAttempt,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionInvoice,
    SubscriptionState,
)
from app.modules.billing.services.gateway import (
    PaymentGatewayError,
    PaymentGatewayNotConfiguredError,
    request_checkout,
)
from app.modules.billing.services.payments import apply_payment_outcome
from app.modules.billing.services.entitlements import (
    check_entitlement,
    get_tenant_entitlements,
    invalidate_entitlements,
)
from app.modules.billing.services.invoicing import generate_eta_subscription_invoice
from app.modules.billing.services.seed import seed_plans
from app.modules.system.dependencies import CurrentUser, require_roles

router = APIRouter(prefix="/billing", tags=["Billing"])


# ── Plan catalogue ─────────────────────────────────────────────────────────────


@router.get("/plans", response_model=list[Plan])
async def list_plans(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    result = await session.execute(select(Plan))
    return result.scalars().all()


@router.post(
    "/plans/seed",
    status_code=status.HTTP_200_OK,
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def seed_plan_catalogue(session: AsyncSession = Depends(get_public_db)):
    """Idempotently seeds the predefined ENTRY/PROFESSIONAL/ENTERPRISE plans."""
    await seed_plans(session)
    result = await session.execute(select(Plan))
    return {"plans": result.scalars().all()}


# ── Subscription ───────────────────────────────────────────────────────────────


class SubscriptionCreateIn(BaseModel):
    plan_code: str
    current_period_end: datetime


@router.get("/subscription", response_model=Subscription | None)
async def get_my_subscription(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    result = await session.execute(
        select(Subscription).where(Subscription.tenant_id == current_user.tenant_id)
    )
    return result.scalar_one_or_none()


@router.post(
    "/subscription",
    response_model=Subscription,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def create_or_change_subscription(
    data: SubscriptionCreateIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """Creates the tenant's subscription, or changes its plan if one already exists."""
    plan = await session.get(Plan, data.plan_code)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan '{data.plan_code}' not found.")

    result = await session.execute(
        select(Subscription).where(Subscription.tenant_id == current_user.tenant_id)
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.plan_code = data.plan_code
        subscription.current_period_end = data.current_period_end
        if subscription.state in (SubscriptionState.SUSPENDED, SubscriptionState.CANCELLED):
            subscription.state = SubscriptionState.ACTIVE
    else:
        subscription = Subscription(
            tenant_id=current_user.tenant_id,
            plan_code=data.plan_code,
            state=SubscriptionState.TRIALING,
            current_period_end=data.current_period_end,
        )
        session.add(subscription)

    await session.commit()
    await session.refresh(subscription)
    await invalidate_entitlements(current_user.tenant_id)
    return subscription


# ── Subscription invoices ────────────────────────────────────────────────────


@router.get("/invoices", response_model=list[SubscriptionInvoice])
async def list_my_invoices(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    sub_result = await session.execute(
        select(Subscription).where(Subscription.tenant_id == current_user.tenant_id)
    )
    subscription = sub_result.scalar_one_or_none()
    if not subscription:
        return []

    result = await session.execute(
        select(SubscriptionInvoice)
        .where(SubscriptionInvoice.subscription_id == subscription.id)
        .order_by(SubscriptionInvoice.created_at.desc())
    )
    return result.scalars().all()


async def _get_owned_invoice(session: AsyncSession, current_user, invoice_id: UUID) -> SubscriptionInvoice:
    invoice = await session.get(SubscriptionInvoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription invoice not found.")
    subscription = await session.get(Subscription, invoice.subscription_id)
    if not subscription or subscription.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription invoice not found.")
    return invoice


@router.get("/invoices/{invoice_id}", response_model=SubscriptionInvoice)
async def get_my_invoice(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    return await _get_owned_invoice(session, current_user, invoice_id)


# ── Payment attempts (gateway webhook target, once Paymob/Fawry/Kashier is wired) ──


class PaymentAttemptIn(BaseModel):
    provider: str
    status: PaymentStatus
    transaction_ref: str | None = None
    error_message: str | None = None


@router.post(
    "/invoices/{invoice_id}/payment-attempts",
    response_model=PaymentAttempt,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment_attempt(
    invoice_id: UUID,
    data: PaymentAttemptIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Records the outcome of a payment attempt against a subscription invoice.

    No live payment gateway is wired yet (FR-863 Paymob/Fawry/Kashier
    integration is still open) — this endpoint does not itself move money.
    It exists so a gateway webhook (once built) or an admin can record a
    real attempt's outcome and drive the real dunning/entitlement engine
    off of it: SUCCEEDED marks the invoice PAID, FAILED invokes
    services.dunning.process_failed_payment (graceful READ_ONLY
    degradation after the grace period — data is never deleted).
    """
    invoice = await _get_owned_invoice(session, current_user, invoice_id)

    return await apply_payment_outcome(
        session,
        invoice=invoice,
        tenant_id=current_user.tenant_id,
        provider=data.provider,
        payment_status=data.status,
        transaction_ref=data.transaction_ref,
        error_message=data.error_message,
    )


@router.post("/invoices/{invoice_id}/checkout")
async def start_checkout(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Closes FR-863: actually initiates a real Paymob charge for this invoice
    (see services.gateway.request_checkout) and returns an iframe_url the
    frontend redirects the merchant to. Creates a PENDING PaymentAttempt
    up front with the Paymob order_id as transaction_ref, so the inbound
    webhook (app.modules.billing.api_webhooks) can find it later.
    """
    invoice = await _get_owned_invoice(session, current_user, invoice_id)
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This invoice is already paid.")

    try:
        checkout = await request_checkout(
            invoice_id=str(invoice.id),
            amount_egp=invoice.amount,
            merchant_email=current_user.email,
            merchant_name=current_user.full_name or current_user.email,
        )
    except PaymentGatewayNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except PaymentGatewayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    attempt = PaymentAttempt(
        invoice_id=invoice.id,
        provider="paymob",
        transaction_ref=str(checkout["order_id"]),
        status=PaymentStatus.PENDING,
    )
    session.add(attempt)
    await session.commit()

    return {"iframe_url": checkout["iframe_url"], "order_id": checkout["order_id"]}


# ── ETA dogfooding (internal — submit our own subscription invoices) ──────────


@router.post(
    "/invoices/{invoice_id}/submit-eta",
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def submit_subscription_invoice_to_eta(
    invoice_id: UUID,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Submits a subscription invoice to the Egyptian Tax Authority under our
    own internal System Tenant's ETA credentials (dogfooding — we are also
    a merchant selling a taxable service). Requires the System Tenant
    (00000000-0000-0000-0000-000000000000) to be seeded first.
    """
    eta_internal_id = await generate_eta_subscription_invoice(session, invoice_id)
    return {"eta_internal_id": eta_internal_id}


# ── Entitlements (Redis-cached, read-through) ──────────────────────────────────


@router.get("/entitlements")
async def get_my_entitlements(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    return await get_tenant_entitlements(session, current_user.tenant_id)


@router.get("/entitlements/{feature_key}")
async def check_my_entitlement(
    feature_key: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    allowed = await check_entitlement(session, current_user.tenant_id, feature_key)
    return {"feature_key": feature_key, "allowed": allowed}
