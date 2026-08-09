"""
app.modules.billing.services.recurring — Subscription Renewal & Dunning Sweep

Closes the other half of the audit finding that started this: even with a
real payment gateway wired (services.gateway), nothing ever GENERATED the
next period's invoice or re-checked an unpaid one — `process_failed_payment`
(services.dunning) existed and worked, but only ever ran when something
explicitly told it a payment failed. A tenant who simply never paid would
sit at whatever state they were last in, forever.

run_billing_cycle() does the two things a real subscription billing system
needs on a schedule:
  1. renew_due_subscriptions(): for every ACTIVE/TRIALING/PAST_DUE
     subscription whose current_period_end has passed, generate the next
     SubscriptionInvoice (due now) and advance current_period_end by one
     billing period — but only if there isn't already an open unpaid
     invoice for them (never double-bill).
  2. sweep_overdue_invoices(): for every still-OPEN invoice past its
     due_date, re-run the real dunning engine (process_failed_payment),
     which is what actually moves a non-paying tenant PAST_DUE -> SUSPENDED
     -> READ_ONLY after the grace period. This is the piece that was
     missing — dunning logic existed but had no trigger except an explicit
     failed payment attempt.

Wired as an ARQ cron job in app.workers.settings (see recurring_billing_cycle).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models.core import (
    InvoiceStatus,
    Plan,
    Subscription,
    SubscriptionInvoice,
    SubscriptionState,
)
from app.modules.billing.services.dunning import process_failed_payment

logger = logging.getLogger(__name__)

BILLING_PERIOD = timedelta(days=30)

_RENEWABLE_STATES = (
    SubscriptionState.TRIALING,
    SubscriptionState.ACTIVE,
    SubscriptionState.PAST_DUE,
)


async def renew_due_subscriptions(session: AsyncSession) -> int:
    """Generates the next period's invoice for every subscription whose
    current_period_end has passed. Returns the number of invoices created."""
    now = datetime.now(UTC)
    result = await session.execute(
        select(Subscription).where(
            Subscription.state.in_(_RENEWABLE_STATES),
            Subscription.current_period_end <= now,
        )
    )
    due_subscriptions = result.scalars().all()

    created = 0
    for subscription in due_subscriptions:
        existing_open = await session.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.subscription_id == subscription.id,
                SubscriptionInvoice.status == InvoiceStatus.OPEN,
            )
        )
        if existing_open.scalars().first():
            # Already has an unpaid invoice outstanding — don't pile on a
            # second one; sweep_overdue_invoices() below handles escalating
            # the existing one. Just push the period marker forward so we
            # don't re-check this subscription every tick.
            subscription.current_period_end = subscription.current_period_end + BILLING_PERIOD
            session.add(subscription)
            continue

        plan = await session.get(Plan, subscription.plan_code)
        if not plan:
            logger.error("Subscription %s references missing plan_code=%s — skipping renewal.", subscription.id, subscription.plan_code)
            continue

        invoice = SubscriptionInvoice(
            subscription_id=subscription.id,
            amount=plan.price_monthly,
            status=InvoiceStatus.OPEN,
            due_date=now,
        )
        session.add(invoice)

        subscription.current_period_end = subscription.current_period_end + BILLING_PERIOD
        session.add(subscription)
        created += 1

        logger.info("Generated renewal invoice for subscription=%s plan=%s amount=%s", subscription.id, plan.code, plan.price_monthly)

    await session.commit()
    return created


async def sweep_overdue_invoices(session: AsyncSession) -> int:
    """Re-runs the dunning engine against every still-OPEN, overdue invoice.
    Returns the number of invoices swept."""
    now = datetime.now(UTC)
    result = await session.execute(
        select(SubscriptionInvoice).where(
            SubscriptionInvoice.status == InvoiceStatus.OPEN,
            SubscriptionInvoice.due_date < now,
        )
    )
    overdue_invoices = result.scalars().all()

    for invoice in overdue_invoices:
        try:
            await process_failed_payment(session, invoice.id)
        except Exception:
            logger.exception("Dunning sweep failed for invoice=%s", invoice.id)

    return len(overdue_invoices)


async def run_billing_cycle(session: AsyncSession) -> dict[str, int]:
    """Entry point for the scheduled worker task."""
    renewed = await renew_due_subscriptions(session)
    swept = await sweep_overdue_invoices(session)
    logger.info("Billing cycle complete: %d invoices generated, %d overdue invoices swept.", renewed, swept)
    return {"invoices_generated": renewed, "invoices_swept": swept}
