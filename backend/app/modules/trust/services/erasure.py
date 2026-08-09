"""
app.modules.trust.services.erasure — Trust Network PDPL Erasure Service (Phase 7a)
"""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trust.models.core import GlobalReputation, TrustContribution
from app.modules.trust.services.hashing import get_vault_pepper, hash_phone_number


async def execute_data_subject_erasure(session: AsyncSession, raw_phone: str) -> bool:
    """
    Executes a hard-delete (right to be forgotten) for a given phone number.
    PDPL strictly prohibits soft-deleting consumer identifiers upon valid erasure requests.
    
    Returns True if records were found and deleted, False otherwise.
    """
    # 1. Securely Hash
    phone_hash = hash_phone_number(raw_phone, pepper=get_vault_pepper())

    # 2. Delete all related TrustContributions (Hard Delete)
    del_contribs = delete(TrustContribution).where(TrustContribution.phone_hash == phone_hash)
    await session.execute(del_contribs)

    # 3. Delete GlobalReputation (Hard Delete)
    del_rep = delete(GlobalReputation).where(GlobalReputation.phone_hash == phone_hash)
    result = await session.execute(del_rep)
    
    await session.flush()

    return result.rowcount > 0
