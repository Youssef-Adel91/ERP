"""
tests.logistics.test_webhook_ingestion — Tests for Idempotent Webhook Ingestion (FR-752)

Tests:
  1. Ingestion service deduplication using CarrierWebhookEvent unique dedupe_key.
  2. Webhook API endpoint returning HTTP 202 Accepted immediately.
"""
from __future__ import annotations

import contextlib

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.logistics.models.carriers import CarrierWebhookEvent
from app.modules.logistics.services.webhooks import ingest_carrier_webhook
from tests.conftest import TEST_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def patched_tenant_session(db_session: AsyncSession, monkeypatch):
    """
    app.modules.logistics.api.webhooks.receive_carrier_webhook opens its
    own tenant_session() directly rather than using Depends(get_tenant_db)
    — deliberately, since TenantMiddleware bypasses this bare webhook path
    entirely (no request.state.tenant_id to resolve get_tenant_db from;
    see that module's docstring for the full "why" — same reasoning as the
    WhatsApp webhook). That means the `client` fixture's normal
    app.dependency_overrides trick can't reach this endpoint's DB access.
    This fixture patches the tenant_session reference imported into the
    webhooks module so it yields the shared test db_session instead of
    opening a real schema_translate_map'd connection (which would try to
    resolve a genuine "tenant_<uuid>" Postgres schema — meaningless on the
    flat, schema-less SQLite test database).
    """
    import app.modules.logistics.api.webhooks as webhooks_module

    @contextlib.asynccontextmanager
    async def _fake_tenant_session(tenant_id):
        yield db_session

    monkeypatch.setattr(webhooks_module, "tenant_session", _fake_tenant_session)
    return db_session


async def test_idempotent_webhook_ingestion(db_session: AsyncSession):
    """
    Verify first webhook ingestion is accepted and duplicate replay is ignored (FR-752).
    """
    tenant_id = str(TEST_TENANT_ID)
    payload = {
        "_id": "bosta_evt_id_555",
        "trackingNumber": "BST-IDEM-01",
        "state": {"value": "DELIVERED"},
    }
    headers = {"x-bosta-signature": ""}

    # 1st Ingestion — Should be Accepted
    res1 = await ingest_carrier_webhook(
        session=db_session,
        tenant_id=tenant_id,
        carrier_code="bosta",
        payload=payload,
        headers=headers,
        raw_bytes=b"{}",
        secret="",
    )
    assert res1["status"] == "accepted"
    assert res1["dedupe_key"] == "bosta:bosta_evt_id_555"
    assert res1["awb_number"] == "BST-IDEM-01"

    # Verify record in DB
    stmt = select(CarrierWebhookEvent).where(CarrierWebhookEvent.dedupe_key == "bosta:bosta_evt_id_555")
    db_evt = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_evt is not None
    assert db_evt.carrier_code == "bosta"

    # 2nd Ingestion (Replay) — Should be Ignored
    res2 = await ingest_carrier_webhook(
        session=db_session,
        tenant_id=tenant_id,
        carrier_code="bosta",
        payload=payload,
        headers=headers,
        raw_bytes=b"{}",
        secret="",
    )
    assert res2["status"] == "ignored"
    assert res2["reason"] == "duplicate_webhook"

    # Verify only 1 record exists in DB
    all_evts = (await db_session.execute(stmt)).scalars().all()
    assert len(all_evts) == 1


async def test_carrier_webhook_endpoint_202(client: AsyncClient, patched_tenant_session: AsyncSession):
    """
    Verify POST /api/v1/webhooks/carriers/{carrier_code} returns HTTP 202 Accepted.

    Updated for the post-security-fix contract (see app.modules.logistics.
    api.webhooks's module docstring): the endpoint now resolves the
    tenant's own CarrierAccount before accepting anything — no account, no
    202 — so this test seeds one first.
    """
    from app.modules.logistics.models.carriers import CarrierAccount

    account = CarrierAccount(
        carrier_code="bosta",
        credentials_ref="vault://secrets/bosta/creds",
        webhook_secret_ref="vault://secrets/bosta/webhook",
        is_active=True,
    )
    patched_tenant_session.add(account)
    await patched_tenant_session.commit()

    payload = {
        "_id": "bosta_evt_endpoint_1",
        "trackingNumber": "BST-API-202",
        "state": {"value": "PICKED_UP"},
    }
    response = await client.post(
        "/api/v1/webhooks/carriers/bosta",
        json=payload,
        headers={"X-Tenant-ID": str(TEST_TENANT_ID)},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["awb_number"] == "BST-API-202"


async def test_carrier_webhook_endpoint_rejects_unconfigured_carrier(
    client: AsyncClient, patched_tenant_session: AsyncSession
):
    """
    Security regression test: without a configured, active CarrierAccount
    for the claimed tenant, the endpoint must reject the webhook (404) —
    NOT silently accept it with a no-op/empty secret like it did before
    the fix. This is the exact vulnerability class that was closed.
    """
    payload = {"_id": "evt_no_account", "trackingNumber": "BST-REJECT", "state": {"value": "PICKED_UP"}}
    response = await client.post(
        "/api/v1/webhooks/carriers/bosta",
        json=payload,
        headers={"X-Tenant-ID": str(TEST_TENANT_ID)},
    )
    assert response.status_code == 404


async def test_carrier_webhook_endpoint_rejects_missing_tenant_id(client: AsyncClient):
    """
    Without X-Tenant-ID (or tenant_id in the payload), must reject with
    400 before touching the database at all — no tenant_session patch
    needed here since the handler returns before ever calling it.
    """
    payload = {"_id": "evt_no_tenant", "trackingNumber": "BST-NOTENANT", "state": {"value": "PICKED_UP"}}
    response = await client.post(
        "/api/v1/webhooks/carriers/bosta",
        json=payload,
        headers={"X-Tenant-ID": ""},
    )
    assert response.status_code == 400
