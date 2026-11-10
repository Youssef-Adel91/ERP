"""Router-level role gates and endpoint-level RBAC tests."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.modules.approvals.api import router as approvals_router
from app.modules.cases.api.vendors import router as vendors_router
from app.modules.contacts.router import router as contacts_router
from app.modules.imports.api.dossiers import router as dossiers_router
from app.modules.inventory.api.items import router as items_router
from app.modules.inventory.api.stock_take import router as stock_take_router
from app.modules.inventory.api.transfer import router as transfer_router
from app.modules.pos.api import router as pos_router
from app.modules.purchasing.api.allocation import router as allocation_router
from app.modules.purchasing.api.orders import router as po_orders_router
from app.modules.reporting.router import router as reporting_router
from app.modules.sales.api.invoices import router as invoices_router
from app.modules.sales.api.orders import router as so_orders_router
from app.plugins.inventory.router import router as plugin_inventory_router
from app.plugins.recruitment.api import router as recruitment_router
from app.plugins.recruitment.api_candidates import router as recruitment_candidates_router
from app.plugins.recruitment.api_interviews import router as recruitment_interviews_router
from app.plugins.travel.api import router as travel_router
from app.plugins.travel.api_packages import router as travel_packages_router
from app.plugins.travel.api_passengers import router as travel_passengers_router
from app.plugins.travel.api_visas import router as travel_visas_router


def _check_for(router):
    deps = [d.dependency for d in router.dependencies]
    assert deps, f"router {router.prefix or router.tags} must carry a role gate"
    return deps[0]


def _req(method, roles):
    return SimpleNamespace(method=method, state=SimpleNamespace(current_user_roles=roles))


@pytest.mark.parametrize(
    "router,allowed,denied",
    [
        (dossiers_router, "ACCOUNTING", "STAFF"),
        (dossiers_router, "ADMIN", "SALES"),
        (stock_take_router, "STAFF", "SALES"),
        (stock_take_router, "OWNER", "ACCOUNTING"),
        (pos_router, "SALES", "ACCOUNTING"),
        (pos_router, "STAFF", "VIEWER"),
        (approvals_router, "STAFF", "VIEWER"),
        (approvals_router, "ACCOUNTING", "ANONYMOUS"),
        (items_router, "STAFF", "SALES"),
        (items_router, "ADMIN", "VIEWER"),
        (transfer_router, "STAFF", "SALES"),
        (transfer_router, "OWNER", "ACCOUNTING"),
        (contacts_router, "SALES", "VIEWER"),
        (contacts_router, "STAFF", "ANONYMOUS"),
        (vendors_router, "ACCOUNTING", "STAFF"),
        (vendors_router, "ADMIN", "SALES"),
        (po_orders_router, "STAFF", "SALES"),
        (po_orders_router, "ACCOUNTING", "VIEWER"),
        (allocation_router, "ACCOUNTING", "STAFF"),
        (allocation_router, "ADMIN", "SALES"),
        (so_orders_router, "SALES", "ACCOUNTING"),
        (so_orders_router, "STAFF", "VIEWER"),
        (invoices_router, "SALES", "STAFF"),
        (invoices_router, "ACCOUNTING", "VIEWER"),
        (reporting_router, "ACCOUNTING", "STAFF"),
        (reporting_router, "ADMIN", "SALES"),
        (plugin_inventory_router, "STAFF", "SALES"),
        (recruitment_router, "STAFF", "SALES"),
        (recruitment_candidates_router, "STAFF", "ACCOUNTING"),
        (recruitment_interviews_router, "STAFF", "SALES"),
        (travel_router, "SALES", "VIEWER"),
        (travel_packages_router, "STAFF", "VIEWER"),
        (travel_passengers_router, "SALES", "VIEWER"),
        (travel_visas_router, "STAFF", "VIEWER"),
    ],
)
def test_write_gate(router, allowed, denied):
    check = _check_for(router)
    asyncio.run(check(_req("GET", [denied])))  # reads stay open
    asyncio.run(check(_req("POST", [allowed])))
    with pytest.raises(HTTPException) as e:
        asyncio.run(check(_req("POST", [denied])))
    assert e.value.status_code == 403


# ── Endpoint-level tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_create_user_and_role_gate_enforcement(client):
    """
    1. OWNER creates a new STAFF user via POST /api/v1/auth/users.
    2. Try creating user with non-owner/admin token -> 403 Forbidden.
    3. Try duplicate email -> 409 Conflict.
    4. Log in as STAFF -> call restricted write endpoint (POST /cases/vendors) -> 403 Forbidden.
    5. Call open read endpoint (GET /cases/vendors) -> 200 OK.
    """
    staff_email = f"staff_{uuid4().hex[:6]}@example.com"
    payload = {
        "email": staff_email,
        "password": "Password123",
        "full_name": "Operational Staff",
        "role": "STAFF",
    }

    # 1. OWNER creates user
    res = await client.post("/api/v1/auth/users", json=payload)
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["email"] == staff_email
    assert created["role"] == "STAFF"

    # 3. Duplicate email -> 409 Conflict
    res_dup = await client.post("/api/v1/auth/users", json=payload)
    assert res_dup.status_code == 409

    # Mint a token for the new STAFF user
    tenant_id = created["tenant_id"]
    staff_user_id = created["id"]
    staff_token = create_access_token(
        user_id=staff_user_id,
        tenant_id=tenant_id,
        roles=["STAFF"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {staff_token}",
            "X-Tenant-ID": tenant_id,
        },
    ) as staff_client:
        # 2. STAFF cannot create users (requires OWNER or ADMIN)
        res_staff_create = await staff_client.post(
            "/api/v1/auth/users",
            json={
                "email": f"substaff_{uuid4().hex[:6]}@example.com",
                "password": "Password123",
                "full_name": "Sub Staff",
                "role": "STAFF",
            },
        )
        assert res_staff_create.status_code == 403

        # 4. STAFF gets 403 on restricted write: POST /cases/vendors (needs OWNER/ADMIN/ACCOUNTING)
        vendor_payload = {
            "name": "Supplier Inc",
            "vendor_type": "airline",
            "is_active": True,
        }
        res_vendor_post = await staff_client.post("/api/v1/cases/vendors", json=vendor_payload)
        assert res_vendor_post.status_code == 403

        # 5. STAFF can perform GET reads on open endpoints
        res_vendor_get = await staff_client.get("/api/v1/cases/vendors")
        assert res_vendor_get.status_code in (200, 404)  # authenticated read allowed through role gate
