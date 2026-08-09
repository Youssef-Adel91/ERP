"""
app/core/dependencies/plugin_gate.py — Plugin Router Access Gate

Enforces the Plugin Marketplace's activation state at the API layer.
Until now, toggling a plugin off in the marketplace (app.modules.system.
api_plugins, PUT /plugins/{key}) persisted real tenant-level intent to
`Tenant.active_plugins`, but the vertical routers themselves — hospitality,
rental, travel, recruitment — stayed mounted unconditionally in main.py and
never checked it. This closes that gap.

Mechanism: a FastAPI dependency, applied via `include_router(...,
dependencies=[require_plugin("travel")])` at the router-mount level in
main.py — NOT global middleware. A per-router dependency is deliberately
the smaller, safer blast radius: it only ever touches the specific routers
it's explicitly attached to, so there is no risk of a middleware regex
mismatch accidentally locking a Core route. Core modules (auth, billing,
inventory, sales, purchasing, cases, trust, eta, approvals, pos, ...) are
never given this dependency and are therefore structurally exempt — not
by an exclusion list this gate has to maintain, but by simply never being
wired to it in the first place.

`require_plugin("<key>")` returns a `Depends(...)` object directly (same
convention as `app.modules.system.dependencies.require_roles`), so callers
use it as `dependencies=[require_plugin("travel")]` — no double-wrapping.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import Tenant


def require_plugin(plugin_key: str):
    """
    Dependency factory: 403s any request under a router mounted with this
    dependency unless `plugin_key` is present in the calling tenant's
    `Tenant.active_plugins`.

    Usage:
        _app.include_router(
            travel_router,
            prefix=f"{settings.API_V1_PREFIX}",
            tags=["Travel Plugin"],
            dependencies=[require_plugin("travel")],
        )
    """

    async def _check_plugin_active(
        current_user: CurrentUser,
        session: AsyncSession = Depends(get_public_db),
    ) -> None:
        tenant = await session.get(Tenant, current_user.tenant_id)
        active_plugins = set(tenant.active_plugins if tenant else [])
        if plugin_key not in active_plugins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Plugin '{plugin_key}' is disabled for this tenant. "
                    f"Enable it in the Marketplace first (PUT /plugins/{plugin_key})."
                ),
            )

    return Depends(_check_plugin_active)
