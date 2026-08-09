"""
app.modules.billing.services.dunning — Dunning and Suspension Engine (Phase 8)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models.core import InvoiceStatus, Subscription, SubscriptionInvoice, SubscriptionState
from app.modules.billing.services.entitlements import invalidate_entitlements
from app.modules.system.models import Tenant, TenantStatus

logger = logging.getLogger(__name__)

# Suspension Thresholds
SUSPENSION_GRACE_PERIOD_DAYS = 14


async def process_failed_payment(session: AsyncSession, invoice_id: UUID) -> None:
    """
    Handles logic when a payment attempt fails for a subscription invoice.
    Enforces graceful degradation to READ_ONLY mode. NEVER deletes tenant data.
    """
    stmt = (
        select(SubscriptionInvoice, Subscription)
        .join(Subscription, SubscriptionInvoice.subscription_id == Subscription.id)
        .where(SubscriptionInvoice.id == invoice_id)
    )
    result = (await session.execute(stmt)).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    invoice, subscription = result
    
    # Calculate days overdue
    now = datetime.now(UTC)
    
    # Make sure due_date is offset-aware for calculation
    due = invoice.due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)

    days_overdue = (now - due).days

    logger.info(f"Processing failed payment for Invoice {invoice_id}. Days overdue: {days_overdue}")

    if days_overdue >= SUSPENSION_GRACE_PERIOD_DAYS:
        # Step 1: Suspend Subscription
        if subscription.state != SubscriptionState.SUSPENDED:
            subscription.state = SubscriptionState.SUSPENDED
            session.add(subscription)
            
            # Step 2: Transition Tenant to READ_ONLY
            tenant = (await session.execute(select(Tenant).where(Tenant.id == subscription.tenant_id))).scalar_one()
            tenant.status = TenantStatus.READ_ONLY
            session.add(tenant)
            
            # Step 3: Invalidate cached entitlements (forces minimal mode on next request)
            await invalidate_entitlements(subscription.tenant_id)
            
            logger.warning(
                f"Tenant {subscription.tenant_id} degraded to READ_ONLY due to non-payment "
                f"({days_overdue} days overdue)."
            )
    else:
        # Within grace period, just mark as PAST_DUE
        if subscription.state != SubscriptionState.PAST_DUE:
            subscription.state = SubscriptionState.PAST_DUE
            session.add(subscription)
            await invalidate_entitlements(subscription.tenant_id)
            
    await session.commit()
