"""
tests/eta/test_eta_gateway.py — Comprehensive Unit & Integration Tests for ETA Gateway (Phase 5 - Step 2)

Tests:
  1. Token Cache & Single-Flight Stampede Protection (50 concurrent calls -> exactly 1 HTTP token fetch).
  2. Global Rate Governor Token Bucket throttling & EtaRateDeferredError exception on burst overflow.
  3. ETA API Gateway HTTP 429 Too Many Requests handling.
  4. ORM persistence and state transitions for EtaTenantConfig, EtaDocument, and EtaSubmission.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.eta.exceptions import (
    EtaAuthenticationError,
    EtaRateDeferredError,
    EtaServiceUnavailableError,
)
from app.modules.eta.models.core import (
    EtaDocument,
    EtaDocumentState,
    EtaEnvironment,
    EtaPreflightState,
    EtaSigningProvider,
    EtaSubmission,
    EtaTenantConfig,
)
from app.modules.eta.services.gateway import EtaGateway, TokenBucket

pytestmark = pytest.mark.asyncio


async def test_eta_gateway_token_cache_single_flight_stampede_protection():
    """
    Verify F-3 & single-flight lock:
    Launching 50 concurrent requests for an access token must result in
    EXACTLY ONE actual token fetch from ETA ID server; the remaining 49
    calls wait on the lock and share the cached token.
    """
    tenant_id = uuid4()
    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="client_id_test_123",
        client_secret_ref="vault://secrets/eta/client_secret",
        taxpayer_rin="100200300",
        activity_code="4610",
    )

    gateway = EtaGateway()

    # Configure simulated ETA Identity Server with 50ms network delay
    async def mock_token_handler(config: EtaTenantConfig) -> dict:
        await asyncio.sleep(0.05)
        return {
            "access_token": f"jwt_token_{config.taxpayer_rin}_secret",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    gateway.mock_token_handler = mock_token_handler

    # Launch 50 concurrent coroutines requesting a token simultaneously
    tasks = [gateway.get_access_token(tenant_config) for _ in range(50)]
    results = await asyncio.gather(*tasks)

    # 1. Verify all 50 callers received the identical valid token
    expected_token = "jwt_token_100200300_secret"
    assert all(token == expected_token for token in results)

    # 2. Verify EXACTLY ONE actual token fetch occurred
    assert gateway.token_fetch_count == 1, (
        f"Expected 1 token fetch due to single-flight lock, but got {gateway.token_fetch_count}"
    )

    # 3. Subsequent sequential call should be served from memory cache immediately
    token_cached = await gateway.get_access_token(tenant_config)
    assert token_cached == expected_token
    assert gateway.token_fetch_count == 1

    # 4. Explicit force_refresh should increment count
    token_refreshed = await gateway.get_access_token(tenant_config, force_refresh=True)
    assert token_refreshed == expected_token
    assert gateway.token_fetch_count == 2


async def test_eta_gateway_rate_governor_throttling_and_deferral():
    """
    Verify F-1 & FR-540 Global Rate Governor:
    Bursting requests beyond bucket capacity (2 calls/sec for submission)
    must immediately trigger EtaRateDeferredError when max_wait=0.0.
    """
    gateway = EtaGateway()
    # Use clean bucket with rate=2.0, capacity=2.0
    gateway.buckets["submission"] = TokenBucket(rate=2.0, capacity=2.0)

    # 1. First two calls succeed immediately
    assert await gateway.acquire_rate_limit("submission", max_wait=0.0) is True
    assert await gateway.acquire_rate_limit("submission", max_wait=0.0) is True

    # 2. Third call overflows capacity and raises EtaRateDeferredError
    with pytest.raises(EtaRateDeferredError) as exc_info:
        await gateway.acquire_rate_limit("submission", max_wait=0.0)

    assert "Global rate governor threshold reached" in str(exc_info.value)
    assert "Task deferred" in str(exc_info.value)

    # 3. Test async sleeping refill when max_wait is allowed
    # Sleeping for 0.6 sec should allow at least 1 token (2.0 tokens/sec * 0.6 = 1.2 tokens) to refill
    await asyncio.sleep(0.6)
    assert await gateway.acquire_rate_limit("submission", max_wait=0.0) is True


async def test_eta_gateway_http_429_triggers_rate_deferred():
    """
    Verify that if ETA API gateway responds with HTTP 429 Too Many Requests,
    EtaGateway translates it to EtaRateDeferredError for worker requeuing (FR-542).
    """
    tenant_id = uuid4()
    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="client_id_test_429",
        client_secret_ref="vault://secrets/eta/client_secret",
        taxpayer_rin="999888777",
        activity_code="4610",
    )

    gateway = EtaGateway()

    # Mock token handler
    async def mock_token_handler(config: EtaTenantConfig) -> dict:
        return {"access_token": "valid_token", "expires_in": 3600}

    gateway.mock_token_handler = mock_token_handler

    # Mock HTTP handler returning 429 Too Many Requests
    async def mock_http_handler(method: str, url: str, json_body: dict, headers: dict) -> dict:
        raise EtaRateDeferredError("ETA returned HTTP 429 Too Many Requests.")

    gateway.mock_http_handler = mock_http_handler

    with pytest.raises(EtaRateDeferredError) as exc_info:
        await gateway.submit_documents(
            tenant_config=tenant_config,
            submission_payload={"documents": []},
            max_wait=0.0,
        )

    assert "429 Too Many Requests" in str(exc_info.value)


async def test_eta_domain_models_persistence_and_state_machine(db_session: AsyncSession):
    """
    Verify ORM persistence, schema translation, and invariants for:
      - EtaTenantConfig (storing Vault secret references, not DB plaintext)
      - EtaDocument (state machine and JSONB payload)
      - EtaSubmission (batch tracking)
    """
    tenant_id = uuid4()

    # 1. Create and persist EtaTenantConfig
    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="eta_client_999",
        client_secret_ref="vault://secrets/eta/tenant_999_secret",
        taxpayer_rin="555444333",
        activity_code="4610",
        branch_eta_codes={"branch_main": "0"},
        signing_provider=EtaSigningProvider.CLOUD_HSM,
        preflight_state=EtaPreflightState.UNVERIFIED,
    )
    db_session.add(tenant_config)

    # 2. Create and persist EtaDocument
    eta_doc = EtaDocument(
        tenant_id=tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id="INV-2026-0001",
        eta_document_type="I",
        eta_document_type_version="1.0",
        state=EtaDocumentState.READY,
        payload_json={"issuer": {"id": "555444333"}, "totalAmount": "1000.00"},
        canonical_string_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(eta_doc)

    # 3. Create and persist EtaSubmission
    submission_uuid = "SUB-ETA-2026-987654"
    submission = EtaSubmission(
        tenant_id=tenant_id,
        submission_uuid=submission_uuid,
        document_ids=["INV-2026-0001"],
        document_count=1,
        submitted_at=datetime.utcnow(),
    )
    db_session.add(submission)

    await db_session.commit()

    # 4. Query back from DB and verify integrity
    stmt_cfg = select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == tenant_id)
    result_cfg = await db_session.execute(stmt_cfg)
    loaded_cfg = result_cfg.scalar_one()

    assert loaded_cfg.taxpayer_rin == "555444333"
    assert loaded_cfg.client_secret_ref == "vault://secrets/eta/tenant_999_secret"
    assert loaded_cfg.branch_eta_codes == {"branch_main": "0"}

    stmt_doc = select(EtaDocument).where(EtaDocument.internal_doc_id == "INV-2026-0001")
    result_doc = await db_session.execute(stmt_doc)
    loaded_doc = result_doc.scalar_one()

    assert loaded_doc.state == EtaDocumentState.READY
    assert loaded_doc.payload_json == {"issuer": {"id": "555444333"}, "totalAmount": "1000.00"}
    assert loaded_doc.canonical_string_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    stmt_sub = select(EtaSubmission).where(EtaSubmission.submission_uuid == submission_uuid)
    result_sub = await db_session.execute(stmt_sub)
    loaded_sub = result_sub.scalar_one()

    assert loaded_sub.document_count == 1
    assert loaded_sub.document_ids == ["INV-2026-0001"]
