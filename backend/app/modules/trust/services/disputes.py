"""
app.modules.trust.services.disputes — Trust Network Dispute Mechanism (Phase 7a)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trust.models.core import TrustContribution
from app.modules.trust.services.scoring import recalculate_global_reputation


async def flag_contribution_as_disputed(session: AsyncSession, contribution_id: UUID) -> bool:
    """
    Flags a specific contribution as disputed and triggers a recalculation
    of the global reputation, which will mathematically exclude this record.
    """
    stmt = select(TrustContribution).where(TrustContribution.id == contribution_id)
    contribution = (await session.execute(stmt)).scalar_one_or_none()

    if not contribution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contribution not found.",
        )

    if contribution.is_disputed:
        return False  # Already disputed

    contribution.is_disputed = True
    session.add(contribution)
    await session.flush()

    # Trigger asynchronous recalculation (here done inline for simplicity,
    # in production this can be dispatched to Celery/ARQ)
    await recalculate_global_reputation(session, contribution.phone_hash)

    return True
