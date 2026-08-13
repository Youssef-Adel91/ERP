"""
app.modules.billing.services.entitlements — Redis-backed Entitlement Engine (Phase 8)
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import _get_redis_client
from app.modules.billing.models.core import Plan, Subscription, SubscriptionState

logger = logging.getLogger(__name__)

ENTITLEMENT_CACHE_TTL = 3600  # 1 hour


async def get_tenant_entitlements(session: AsyncSession, tenant_id: UUID) -> dict:
    """
    Fetches tenant entitlements, preferring Redis cache.
    If not in cache, loads from DB and caches it.
    """
    cache_key = f"entitlements:{tenant_id}"
    
    # 1. Check Redis
    rc = await _get_redis_client()
    cached_data = await rc.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    # 2. Cache Miss: Read from DB
    stmt = (
        select(Plan.entitlements)
        .join(Subscription, Subscription.plan_code == Plan.code)
        .where(Subscription.tenant_id == tenant_id)
        # We allow entitlements if ACTIVE or TRIALING or PAST_DUE.
        # If SUSPENDED or CANCELLED, we return minimal/empty entitlements or handle differently.
        .where(Subscription.state.in_([SubscriptionState.ACTIVE, SubscriptionState.TRIALING, SubscriptionState.PAST_DUE]))
    )
    entitlements = (await session.execute(stmt)).scalar_one_or_none()

    if entitlements is None:
        # Fallback empty or default entitlements
        entitlements = {}

    # 3. Cache in Redis
    rc = await _get_redis_client()
    await rc.setex(cache_key, ENTITLEMENT_CACHE_TTL, json.dumps(entitlements))
    
    return entitlements


async def check_entitlement(session: AsyncSession, tenant_id: UUID, feature_key: str) -> bool:
    """
    Strict server-side check to see if a tenant has access to a specific feature.
    """
    entitlements = await get_tenant_entitlements(session, tenant_id)
    return entitlements.get(feature_key, False)


async def invalidate_entitlements(tenant_id: UUID) -> None:
    """
    Clears the Redis cache for a tenant. Called on plan upgrade/downgrade or suspension.
    """
    cache_key = f"entitlements:{tenant_id}"
    rc = await _get_redis_client()
    await rc.delete(cache_key)
    logger.info(f"Invalidated entitlement cache for tenant {tenant_id}")
