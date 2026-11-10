"""Tests for the tenant provisioning 503 holding gate and startup reconciler."""
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db.database import _get_redis_client
from app.core.security import create_access_token
from app.main import app
from app.modules.system.models import PlanTier, ProvisioningState, Tenant, TenantStatus
from app.modules.system.router import reconcile_orphaned_provisioning


@pytest.mark.asyncio
async def test_provisioning_503_gate_and_states(client, db_session):
    """
    Verify:
    1. When Redis flag 'tenant:provisioning:<id>' is 'pending', API returns 503 TENANT_PROVISIONING.
    2. When Redis flag is 'failed', API returns 503 TENANT_PROVISIONING_FAILED.
    3. Auth endpoints (/api/v1/auth) bypass the gate so users can check status/refresh.
    4. When Redis flag is cleared, requests proceed normally.
    """
    test_tid = str(uuid4())
    token = create_access_token(user_id=uuid4(), tenant_id=test_tid, roles=["OWNER"])
    rc = await _get_redis_client()
    key = f"tenant:provisioning:{test_tid}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        # Case 1: Flag is pending -> 503 TENANT_PROVISIONING
        await rc.set(key, "pending")
        res = await ac.get("/api/v1/contacts")
        assert res.status_code == 503
        data = res.json()
        assert data.get("code") == "TENANT_PROVISIONING"
        assert res.headers.get("Retry-After") == "5"

        # Case 2: Auth endpoint /api/v1/auth/me bypasses the gate
        res_auth = await ac.get("/api/v1/auth/me")
        # May be 200 or 401 depending on user existing in DB, but NOT 503
        assert res_auth.status_code != 503

        # Case 3: Flag is failed -> 503 TENANT_PROVISIONING_FAILED
        await rc.set(key, "failed")
        res_failed = await ac.get("/api/v1/contacts")
        assert res_failed.status_code == 503
        data_failed = res_failed.json()
        assert data_failed.get("code") == "TENANT_PROVISIONING_FAILED"

        # Case 4: Flag cleared -> returns non-503 (normal response)
        await rc.delete(key)
        res_cleared = await ac.get("/api/v1/contacts")
        assert res_cleared.status_code != 503


@pytest.mark.asyncio
async def test_reconciler_clears_orphan_for_active_tenant(db_session):
    """
    When a tenant has completed provisioning in DB but its Redis key was left pending,
    reconcile_orphaned_provisioning() clears the orphaned Redis key.
    """
    tid = uuid4()
    tenant = Tenant(
        id=tid,
        name="Reconciled Merchant",
        slug=f"reconciled-{tid.hex[:6]}",
        schema_name=f"tenant_{tid.hex}",
        status=TenantStatus.ACTIVE,
        provisioning_state=ProvisioningState.SEQUENCES_CREATED,
        plan=PlanTier.FREE,
    )
    db_session.add(tenant)
    await db_session.commit()

    rc = await _get_redis_client()
    key = f"tenant:provisioning:{tid}"
    await rc.set(key, "pending")

    await reconcile_orphaned_provisioning()

    # The key should now be removed
    val = await rc.get(key)
    assert val is None


@pytest.mark.asyncio
async def test_reconciler_clears_orphan_for_nonexistent_tenant():
    """
    When a Redis key references a non-existent tenant (e.g. failed/deleted registration),
    reconcile_orphaned_provisioning() cleans up the orphan.
    """
    phantom_tid = uuid4()
    rc = await _get_redis_client()
    key = f"tenant:provisioning:{phantom_tid}"
    await rc.set(key, "pending")

    await reconcile_orphaned_provisioning()

    val = await rc.get(key)
    assert val is None
