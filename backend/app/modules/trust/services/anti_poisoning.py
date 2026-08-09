"""
app.modules.trust.services.anti_poisoning — Trust Network Defense Engine (Phase 7a)
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trust.models.core import ShipmentOutcome, TrustContribution
from app.modules.trust.services.scoring import recalculate_global_reputation

logger = logging.getLogger(__name__)


async def run_anti_poisoning_scan(session: AsyncSession) -> dict[str, int]:
    """
    Background job to detect and neutralize malicious tenants attempting
    to poison the Trust Network (e.g., mass-reporting fake returns to harm competitors).
    
    Logic:
    - Analyzes tenants with > 50 contributions.
    - If a tenant's RETURNED + REFUSED rate is > 95% (a wild statistical outlier), 
      their contributions are down-weighted to 0.0, neutralizing their impact on the network.
      
    Returns a dict with statistics of the scan.
    """
    # 1. Aggregate statistics per tenant
    stmt = (
        select(
            TrustContribution.tenant_id,
            func.count(TrustContribution.id).label("total_reports"),
            func.sum(
                case(
                    (TrustContribution.outcome.in_([ShipmentOutcome.RETURNED, ShipmentOutcome.REFUSED]), 1),
                    else_=0
                )
            ).label("negative_reports"),
        )
        .where(TrustContribution.is_disputed == False)
        .group_by(TrustContribution.tenant_id)
        .having(func.count(TrustContribution.id) >= 50)  # Minimum volume threshold
    )
    
    results = await session.execute(stmt)
    
    poisoned_tenants_detected = 0
    contributions_neutralized = 0

    for row in results.all():
        tenant_id, total, negative = row
        return_rate = Decimal(negative) / Decimal(total)

        if return_rate >= Decimal("0.95"):
            # This tenant is a statistical anomaly (95%+ negative outcome rate across 50+ shipments)
            logger.warning(f"Anti-Poisoning: Tenant {tenant_id} flagged as anomalous (rate: {return_rate}). Down-weighting.")
            
            # Neutralize weights
            upd_stmt = (
                update(TrustContribution)
                .where(TrustContribution.tenant_id == tenant_id)
                .where(TrustContribution.weight > Decimal("0.0000"))
                .values(weight=Decimal("0.0000"))
                .returning(TrustContribution.phone_hash)
            )
            
            affected_hashes_result = await session.execute(upd_stmt)
            affected_hashes = set(affected_hashes_result.scalars().all())
            
            poisoned_tenants_detected += 1
            contributions_neutralized += len(affected_hashes)

            # Trigger recalculation for affected global hashes
            for p_hash in affected_hashes:
                await recalculate_global_reputation(session, p_hash)

    await session.commit()
    
    return {
        "poisoned_tenants": poisoned_tenants_detected,
        "neutralized_contributions": contributions_neutralized,
    }
