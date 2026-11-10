"""Router-level role gates added for POS, stock-take and import dossiers."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.imports.api.dossiers import router as dossiers_router
from app.modules.inventory.api.stock_take import router as stock_take_router
from app.modules.pos.api import router as pos_router


def _check_for(router):
    deps = [d.dependency for d in router.dependencies]
    assert deps, "router must carry a role gate"
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
    ],
)
def test_write_gate(router, allowed, denied):
    check = _check_for(router)
    asyncio.run(check(_req("GET", [denied])))  # reads stay open
    asyncio.run(check(_req("POST", [allowed])))
    with pytest.raises(HTTPException) as e:
        asyncio.run(check(_req("POST", [denied])))
    assert e.value.status_code == 403
