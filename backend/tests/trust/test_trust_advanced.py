"""
tests.trust.test_trust_advanced — Verification for Advanced Compliance (Phase 7a)
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trust.models.core import GlobalReputation, ShipmentOutcome, TrustContribution, TrustRiskBand
from app.modules.trust.services.anti_poisoning import run_anti_poisoning_scan
from app.modules.trust.services.disputes import flag_contribution_as_disputed
from app.modules.trust.services.erasure import execute_data_subject_erasure
from app.modules.trust.services.hashing import hash_phone_number
from app.modules.trust.services.scoring import record_contribution

pytestmark = pytest.mark.asyncio


async def test_execute_data_subject_erasure(db_session: AsyncSession):
    """Verify that a valid erasure request completely hard-deletes the records."""
    tenant_id = str(uuid4())
    raw_phone = "01099998888"
    phone_hash = hash_phone_number(raw_phone)

    # 1. Add data
    await record_contribution(db_session, phone_hash, tenant_id, ShipmentOutcome.DELIVERED)

    # Verify exists
    assert (await db_session.execute(select(GlobalReputation).where(GlobalReputation.phone_hash == phone_hash))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(TrustContribution).where(TrustContribution.phone_hash == phone_hash))).scalars().first() is not None

    # 2. Execute Erasure
    erased = await execute_data_subject_erasure(db_session, raw_phone)
    assert erased is True

    # 3. Verify Hard Deletion
    assert (await db_session.execute(select(GlobalReputation).where(GlobalReputation.phone_hash == phone_hash))).scalar_one_or_none() is None
    assert (await db_session.execute(select(TrustContribution).where(TrustContribution.phone_hash == phone_hash))).scalars().first() is None


async def test_flag_contribution_as_disputed(db_session: AsyncSession):
    """Verify that disputing a contribution excludes it from the GlobalReputation score."""
    tenant_1 = str(uuid4())
    tenant_2 = str(uuid4())
    tenant_3 = str(uuid4())
    
    raw_phone = "01122224444"
    phone_hash = hash_phone_number(raw_phone)

    # Create K=3 scenario
    await record_contribution(db_session, phone_hash, tenant_1, ShipmentOutcome.DELIVERED)
    await record_contribution(db_session, phone_hash, tenant_2, ShipmentOutcome.DELIVERED)
    await record_contribution(db_session, phone_hash, tenant_3, ShipmentOutcome.RETURNED)

    # Get the reputation (1 return out of 3 = 33% -> HIGH_RISK or CAUTION)
    rep = (await db_session.execute(select(GlobalReputation).where(GlobalReputation.phone_hash == phone_hash))).scalar_one()
    assert rep.distinct_tenant_count == 3
    assert rep.band == TrustRiskBand.HIGH_RISK

    # Find the RETURNED contribution
    contribs = (await db_session.execute(select(TrustContribution).where(TrustContribution.phone_hash == phone_hash))).scalars().all()
    returned_contrib = next(c for c in contribs if c.outcome == ShipmentOutcome.RETURNED)

    # Flag as disputed
    await flag_contribution_as_disputed(db_session, returned_contrib.id)

    # Verify the global reputation dropped back to K=2 and UNKNOWN!
    await db_session.refresh(rep)
    assert rep.distinct_tenant_count == 2
    assert rep.band == TrustRiskBand.UNKNOWN


async def test_anti_poisoning_engine(db_session: AsyncSession):
    """Verify that a malicious tenant is detected and weights are dropped to 0."""
    malicious_tenant = str(uuid4())
    good_tenant = str(uuid4())

    # Create 55 returned contributions for malicious tenant (outlier)
    for i in range(55):
        phone_hash = hash_phone_number(f"010000{i:05d}")
        await record_contribution(db_session, phone_hash, malicious_tenant, ShipmentOutcome.RETURNED)

    # Create 52 delivered contributions for good tenant
    for i in range(52):
        phone_hash = hash_phone_number(f"011000{i:05d}")
        await record_contribution(db_session, phone_hash, good_tenant, ShipmentOutcome.DELIVERED)

    # Run Anti-Poisoning Scan
    stats = await run_anti_poisoning_scan(db_session)
    
    assert stats["poisoned_tenants"] == 1
    assert stats["neutralized_contributions"] == 55

    # Verify malicious weights are 0.0
    malicious_contribs = (await db_session.execute(
        select(TrustContribution).where(TrustContribution.tenant_id == malicious_tenant)
    )).scalars().all()
    for c in malicious_contribs:
        assert c.weight == Decimal("0.0000")

    # Verify good weights are still 1.0
    good_contribs = (await db_session.execute(
        select(TrustContribution).where(TrustContribution.tenant_id == good_tenant)
    )).scalars().all()
    for c in good_contribs:
        assert c.weight == Decimal("1.0000")


async def test_pepper_rotation_job(db_session: AsyncSession, seed_tenant_and_users):
    """
    Verify that the pepper rotation job iterates through tenant schemas,
    reads Contacts, and correctly migrates GlobalReputation and TrustContribution
    hashes to the new pepper version.
    """
    from app.modules.contacts.models import Contact
    from app.modules.trust.services.pepper_rotation import rotate_pepper_job
    from tests.conftest import TEST_TENANT_ID

    raw_phone = "01234567890"
    old_pepper = "OLD_PEPPER_1"
    new_pepper = "NEW_PEPPER_2"

    old_hash = hash_phone_number(raw_phone, pepper=old_pepper)
    new_hash = hash_phone_number(raw_phone, pepper=new_pepper)

    # 1. Seed a Contact in the test tenant DB
    contact = Contact(
        id=uuid4(), 
        tenant_id=TEST_TENANT_ID, 
        name="Rotation Test", 
        phone=raw_phone,
        contact_type="CUSTOMER"
    )
    db_session.add(contact)
    
    # 2. Add Trust records for the OLD hash
    await record_contribution(db_session, old_hash, str(TEST_TENANT_ID), ShipmentOutcome.DELIVERED)

    # 3. Mock sessions and Run Rotation
    from unittest.mock import patch
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session(*args, **kwargs):
        yield db_session

    with patch("app.modules.trust.services.pepper_rotation.public_session", mock_session), \
         patch("app.modules.trust.services.pepper_rotation.tenant_session", mock_session):
        stats = await rotate_pepper_job(old_pepper, new_pepper, new_version=2)

    assert stats["hashes_migrated"] == 1
    assert stats["contributions_migrated"] == 1

    # 4. Verify Migration
    old_rep = (await db_session.execute(select(GlobalReputation).where(GlobalReputation.phone_hash == old_hash))).scalar_one_or_none()
    new_rep = (await db_session.execute(select(GlobalReputation).where(GlobalReputation.phone_hash == new_hash))).scalar_one_or_none()

    assert old_rep is not None  # Old rep stays until naturally purged, but stats might be zeroed (actually stats are un-touched during migration directly)
    assert new_rep is not None
    assert new_rep.pepper_version == 2

    # Old contributions should be 0, new should be 1
    old_contribs = (await db_session.execute(select(TrustContribution).where(TrustContribution.phone_hash == old_hash))).scalars().all()
    new_contribs = (await db_session.execute(select(TrustContribution).where(TrustContribution.phone_hash == new_hash))).scalars().all()

    assert len(old_contribs) == 0
    assert len(new_contribs) == 1

