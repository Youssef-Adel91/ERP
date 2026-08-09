"""
tests.billing.test_billing — Tests for Billing & Monetisation Engine (Phase 8)
"""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models.core import Plan, PlanTier, Subscription, SubscriptionInvoice, SubscriptionState
from app.modules.billing.services.dunning import process_failed_payment
from app.modules.billing.services.entitlements import check_entitlement, get_tenant_entitlements, invalidate_entitlements
from app.modules.billing.services.invoicing import INTERNAL_SYSTEM_TENANT_ID, generate_eta_subscription_invoice
from app.modules.system.models import Tenant, TenantStatus

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def seeded_billing(db_session: AsyncSession, seed_tenant_and_users):
    """Fixture to seed a test plan and subscription."""
    from tests.conftest import TEST_TENANT_ID
    
    plan = Plan(
        code="TEST_PRO",
        tier=PlanTier.PROFESSIONAL,
        price_monthly=Decimal("99.00"),
        entitlements={"multi_branch": True, "approval_workflows": False}
    )
    db_session.add(plan)
    
    subscription = Subscription(
        id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        plan_code=plan.code,
        state=SubscriptionState.ACTIVE,
        current_period_end=datetime.now(UTC) + timedelta(days=30)
    )
    db_session.add(subscription)
    
    invoice = SubscriptionInvoice(
        id=uuid4(),
        subscription_id=subscription.id,
        amount=Decimal("99.00"),
        due_date=datetime.now(UTC) - timedelta(days=15)  # 15 days overdue
    )
    db_session.add(invoice)
    await db_session.commit()
    
    return {"plan": plan, "subscription": subscription, "invoice": invoice, "tenant_id": TEST_TENANT_ID}


async def test_entitlement_engine_redis_caching(db_session: AsyncSession, seeded_billing):
    tenant_id = seeded_billing["tenant_id"]
    
    with patch("app.modules.billing.services.entitlements.redis_client") as mock_redis:
        # Mock Cache Miss
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()
        
        entitlements = await get_tenant_entitlements(db_session, tenant_id)
        
        assert entitlements["multi_branch"] is True
        assert entitlements["approval_workflows"] is False
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_called_once()

        # Mock Cache Hit
        mock_redis.get.reset_mock()
        mock_redis.get = AsyncMock(return_value=json.dumps({"multi_branch": True}))
        
        has_feature = await check_entitlement(db_session, tenant_id, "multi_branch")
        assert has_feature is True
        mock_redis.get.assert_called_once()


async def test_dunning_suspends_tenant_gracefully(db_session: AsyncSession, seeded_billing):
    tenant_id = seeded_billing["tenant_id"]
    invoice_id = seeded_billing["invoice"].id
    
    # Process the failed payment (which is 15 days overdue, triggering > 14 days grace period rule)
    with patch("app.modules.billing.services.entitlements.redis_client") as mock_redis:
        mock_redis.delete = AsyncMock()
        
        await process_failed_payment(db_session, invoice_id)
        
        # Verify Subscription State
        sub = (await db_session.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))).scalar_one()
        assert sub.state == SubscriptionState.SUSPENDED
        
        # Verify Tenant State (READ_ONLY, NOT deleted)
        tenant = (await db_session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        assert tenant.status == TenantStatus.READ_ONLY
        assert tenant.deleted_at is None
        
        # Verify Cache Invalidation
        mock_redis.delete.assert_called_once()


async def test_dogfooding_eta_invoice_generation(db_session: AsyncSession, seeded_billing):
    # Seed the internal system tenant
    system_tenant = Tenant(
        id=INTERNAL_SYSTEM_TENANT_ID,
        name="Dogfood ERP Co",
        slug="dogfood",
        schema_name="dogfood",
        status=TenantStatus.ACTIVE
    )
    db_session.add(system_tenant)
    await db_session.commit()
    
    invoice_id = seeded_billing["invoice"].id
    
    eta_uuid = await generate_eta_subscription_invoice(db_session, invoice_id)
    assert eta_uuid == f"ETA-MOCK-{invoice_id}"
