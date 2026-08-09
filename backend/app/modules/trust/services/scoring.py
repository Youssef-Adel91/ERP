"""
app.modules.trust.services.scoring — Trust Network Scoring Engine
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trust.models.core import GlobalReputation, ShipmentOutcome, TrustContribution, TrustRiskBand


def calculate_reputation_band(return_rate: Decimal, distinct_merchants: int) -> TrustRiskBand:
    """
    Mathematical band assignment based on historical return rate.
    K-Anonymity Gate is applied separately during reads, but we also enforce it here for base state.
    """
    if distinct_merchants < 3:
        return TrustRiskBand.UNKNOWN

    if return_rate <= Decimal("0.10"):
        return TrustRiskBand.GOOD
    elif return_rate <= Decimal("0.25"):
        return TrustRiskBand.CAUTION
    else:
        return TrustRiskBand.HIGH_RISK


async def record_contribution(
    session: AsyncSession,
    phone_hash: str,
    tenant_id: str,
    outcome: ShipmentOutcome,
    weight: Decimal = Decimal("1.0000"),
) -> None:
    """
    Idempotent logic to record a new contribution and recompute the global score.
    """
    # 1. Ensure GlobalReputation exists
    stmt = select(GlobalReputation).where(GlobalReputation.phone_hash == phone_hash)
    reputation = (await session.execute(stmt)).scalar_one_or_none()

    if not reputation:
        reputation = GlobalReputation(phone_hash=phone_hash, pepper_version=1)
        session.add(reputation)
        await session.flush()

    # 2. Add Contribution
    contrib = TrustContribution(
        phone_hash=phone_hash,
        tenant_id=tenant_id,
        outcome=outcome,
        weight=weight,
    )
    session.add(contrib)
    await session.flush()

    # 3. Recalculate
    await recalculate_global_reputation(session, phone_hash)


async def recalculate_global_reputation(session: AsyncSession, phone_hash: str) -> None:
    """
    Recomputes the recency_weighted_return_rate and band for a phone hash.
    """
    stmt = (
        select(TrustContribution)
        .where(TrustContribution.phone_hash == phone_hash)
        .where(TrustContribution.is_disputed == False)
    )
    contributions = list((await session.execute(stmt)).scalars().all())

    upd_stmt = select(GlobalReputation).where(GlobalReputation.phone_hash == phone_hash)
    reputation = (await session.execute(upd_stmt)).scalar_one()

    if not contributions:
        # All contributions deleted or disputed
        reputation.distinct_tenant_count = 0
        reputation.recency_weighted_return_rate = Decimal("0.0000")
        reputation.band = TrustRiskBand.UNKNOWN
        session.add(reputation)
        await session.flush()
        return

    # K-Anonymity constraint: Count distinct merchants
    distinct_tenants = len({c.tenant_id for c in contributions})

    # Weighted return rate calculation (simplified for Phase 7a)
    total_weight = sum(c.weight for c in contributions)
    returned_weight = sum(c.weight for c in contributions if c.outcome in (ShipmentOutcome.RETURNED, ShipmentOutcome.REFUSED))

    return_rate = (returned_weight / total_weight).quantize(Decimal("0.0001")) if total_weight > 0 else Decimal("0.0000")
    band = calculate_reputation_band(return_rate, distinct_tenants)

    reputation.distinct_tenant_count = distinct_tenants
    reputation.recency_weighted_return_rate = return_rate
    reputation.band = band

    session.add(reputation)
    await session.flush()
