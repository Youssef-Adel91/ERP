"""
tests.trust.test_trust_network — Verification for Trust Network Privacy & Scoring (Phase 7a)
"""
from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trust.models.core import GlobalReputation, ShipmentOutcome, TrustRiskBand
from app.modules.trust.services.gates import query_reputation
from app.modules.trust.services.hashing import get_vault_pepper, hash_phone_number
from app.modules.trust.services.scoring import calculate_reputation_band, record_contribution

pytestmark = pytest.mark.asyncio


def test_phone_hashing_and_vault_pepper():
    """Verify phone numbers are correctly normalized and HMAC-SHA256 hashed."""
    pepper = get_vault_pepper()
    assert pepper is not None

    # Normalization: "+20 10-1234-5678" -> "201012345678"
    raw_phone = "+20 10-1234-5678"
    hashed = hash_phone_number(raw_phone, pepper)
    
    # Manual verify
    normalized_expected = "201012345678"
    expected_hash = hmac.new(pepper.encode("utf-8"), normalized_expected.encode("utf-8"), digestmod=sha256).hexdigest()
    
    assert hashed == expected_hash

    # Test local number fallback (01012345678 -> 201012345678)
    local_phone = "01012345678"
    assert hash_phone_number(local_phone, pepper) == expected_hash


async def test_reciprocity_gate(db_session: AsyncSession):
    """
    Verify that a tenant without recent contributions (last 30 days) 
    is blocked from querying the Trust Network (FR-712).
    """
    tenant_id = str(uuid4())
    raw_phone = "01099999999"

    # 1. No contributions -> Should raise 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        await query_reputation(db_session, tenant_id, raw_phone)
    
    assert exc_info.value.status_code == 403
    assert "Reciprocity Gate" in exc_info.value.detail

    # 2. Add a recent contribution
    phone_hash = hash_phone_number(raw_phone)
    await record_contribution(
        session=db_session,
        phone_hash=phone_hash,
        tenant_id=tenant_id,
        outcome=ShipmentOutcome.DELIVERED,
    )

    # 3. Query should now succeed
    res = await query_reputation(db_session, tenant_id, raw_phone)
    # Still UNKNOWN because k < 3, but NO 403 error!
    assert res["band"] == TrustRiskBand.UNKNOWN.value


async def test_k_anonymity_gate_and_scoring(db_session: AsyncSession):
    """
    Verify that scores are masked as UNKNOWN until distinct_tenant_count >= 3.
    Once k=3, verify risk band calculations.
    """
    tenant_1 = str(uuid4())
    tenant_2 = str(uuid4())
    tenant_3 = str(uuid4())
    
    raw_phone = "01122223333"
    phone_hash = hash_phone_number(raw_phone)

    # Tenant 1 contributes (RETURNED)
    await record_contribution(db_session, phone_hash, tenant_1, ShipmentOutcome.RETURNED)
    
    # Query (has reciprocity, but k=1)
    res = await query_reputation(db_session, tenant_1, raw_phone)
    assert res["band"] == TrustRiskBand.UNKNOWN.value

    # Tenant 2 contributes (RETURNED)
    await record_contribution(db_session, phone_hash, tenant_2, ShipmentOutcome.RETURNED)
    
    # Query (k=2)
    res = await query_reputation(db_session, tenant_2, raw_phone)
    assert res["band"] == TrustRiskBand.UNKNOWN.value

    # Tenant 3 contributes (DELIVERED) -> now k=3!
    await record_contribution(db_session, phone_hash, tenant_3, ShipmentOutcome.DELIVERED)

    # Query (k=3)
    # Total weights = 3. Returned = 2. Return rate = 66% -> HIGH_RISK
    res = await query_reputation(db_session, tenant_3, raw_phone)
    assert res["band"] == TrustRiskBand.HIGH_RISK.value
    assert "مخاطرة عالية" in res["explanation"]


def test_calculate_reputation_band():
    """Verify the internal math rules for band assignment."""
    # Enforces K-Anonymity inside math core as well
    assert calculate_reputation_band(Decimal("0.05"), 2) == TrustRiskBand.UNKNOWN
    
    assert calculate_reputation_band(Decimal("0.05"), 3) == TrustRiskBand.GOOD
    assert calculate_reputation_band(Decimal("0.20"), 3) == TrustRiskBand.CAUTION
    assert calculate_reputation_band(Decimal("0.50"), 3) == TrustRiskBand.HIGH_RISK
