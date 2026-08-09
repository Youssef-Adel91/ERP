"""
app.modules.trust.services.pepper_rotation — Trust Network Key Rotation (Phase 7a)
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import public_session, tenant_session
from app.modules.contacts.models import Contact
from app.modules.system.models import Tenant
from app.modules.trust.models.core import GlobalReputation, TrustContribution
from app.modules.trust.services.hashing import hash_phone_number

logger = logging.getLogger(__name__)


async def rotate_pepper_job(old_pepper: str, new_pepper: str, new_version: int) -> dict[str, int]:
    """
    Background worker to rotate the HMAC-SHA256 pepper for the Trust Network.
    
    Because the Trust Network only stores hashes (zero PII), we cannot mathematically
    reverse the hashes to apply the new pepper. Instead, we must read the plaintext
    phone numbers from the isolated tenant schemas, calculate both hashes, and
    migrate the global records.
    
    Orphaned records (where the merchant deleted the underlying plaintext contact)
    will simply age out naturally.
    """
    logger.info(f"Starting Trust Network pepper rotation to version {new_version}")

    hashes_migrated = 0
    contributions_migrated = 0

    async with public_session() as p_session:
        # Get all active tenants
        tenants = (await p_session.execute(select(Tenant))).scalars().all()

        for tenant in tenants:
            logger.info(f"Rotating pepper for tenant: {tenant.id}")

            async with tenant_session(tenant.id) as t_session:
                # 1. Fetch all distinct phone numbers in this tenant
                stmt = select(Contact.phone).where(Contact.phone.is_not(None)).distinct()
                phones = (await t_session.execute(stmt)).scalars().all()

                for raw_phone in phones:
                    try:
                        old_hash = hash_phone_number(raw_phone, pepper=old_pepper)
                        new_hash = hash_phone_number(raw_phone, pepper=new_pepper)

                        if old_hash == new_hash:
                            continue

                        # 2. Migrate GlobalReputation
                        # We only create a new GlobalReputation if it doesn't exist.
                        # We don't delete the old one immediately (it will age out).
                        # The old contributions will move to the new hash.
                        
                        # Find existing new_hash reputation
                        new_rep_stmt = select(GlobalReputation).where(GlobalReputation.phone_hash == new_hash)
                        new_rep = (await p_session.execute(new_rep_stmt)).scalar_one_or_none()

                        if not new_rep:
                            old_rep_stmt = select(GlobalReputation).where(GlobalReputation.phone_hash == old_hash)
                            old_rep = (await p_session.execute(old_rep_stmt)).scalar_one_or_none()
                            
                            if old_rep:
                                # Clone basic attributes, wait for recalculation to fix stats
                                new_rep = GlobalReputation(
                                    phone_hash=new_hash,
                                    pepper_version=new_version,
                                )
                                p_session.add(new_rep)
                                hashes_migrated += 1
                        
                        # 3. Migrate TrustContributions
                        upd_contribs = (
                            update(TrustContribution)
                            .where(TrustContribution.phone_hash == old_hash)
                            .values(phone_hash=new_hash)
                        )
                        res = await p_session.execute(upd_contribs)
                        contributions_migrated += res.rowcount

                    except ValueError:
                        # Skip invalid phone formats during rotation
                        continue
                
                # Commit public schema changes for this tenant batch
                await p_session.commit()

    logger.info(f"Rotation complete. Migrated {hashes_migrated} unique hashes and {contributions_migrated} contributions.")
    
    return {
        "hashes_migrated": hashes_migrated,
        "contributions_migrated": contributions_migrated,
    }
