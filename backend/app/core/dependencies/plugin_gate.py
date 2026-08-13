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

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import Tenant

# Fixed number of mutating (create/update/delete) requests a tenant may make
# against a plugin while it's only in demo mode (not fully activated), per
# explicit product decision: one flat limit shared by every plugin rather
# than a per-plugin or time-based one. GET/HEAD/OPTIONS requests (browsing,
# viewing demo data) are never counted or blocked — the cap only applies to
# actions that create/change data, matching "جرّب الديمو" being a real but
# bounded trial rather than a read-only preview.
DEMO_OPERATION_LIMIT = 10
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def require_plugin(plugin_key: str):
    """
    Dependency factory: 403s any request under a router mounted with this
    dependency unless `plugin_key` is present in the calling tenant's
    `Tenant.active_plugins` (fully activated) or `Tenant.demo_plugins`
    (free trial, capped at DEMO_OPERATION_LIMIT mutating requests — see
    Tenant.demo_usage).

    Usage:
        _app.include_router(
            travel_router,
            prefix=f"{settings.API_V1_PREFIX}",
            tags=["Travel Plugin"],
            dependencies=[require_plugin("travel")],
        )
    """

    async def _check_plugin_active(
        request: Request,
        current_user: CurrentUser,
        session: AsyncSession = Depends(get_public_db),
    ) -> None:
        tenant = await session.get(Tenant, current_user.tenant_id)
        active_plugins = set(tenant.active_plugins if tenant else [])
        demo_plugins = set(tenant.demo_plugins if tenant else [])

        if plugin_key in active_plugins:
            return  # Fully activated — no demo cap applies.

        if plugin_key not in demo_plugins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Plugin '{plugin_key}' is disabled for this tenant. "
                    f"Enable it in the Marketplace first (PUT /plugins/{plugin_key}), "
                    f"or try it free (POST /plugins/{plugin_key}/demo)."
                ),
            )

        # In demo mode — reads are unlimited, only mutating requests count
        # against the shared DEMO_OPERATION_LIMIT.
        if request.method not in _MUTATING_METHODS:
            return

        usage = dict(tenant.demo_usage or {})
        used = usage.get(plugin_key, 0)
        if used >= DEMO_OPERATION_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "انتهت حدود التجربة المجانية لهذا النظام "
                    f"({DEMO_OPERATION_LIMIT} عمليات). فعّل النظام بالكامل "
                    f"من صفحة الأنظمة أو (PUT /plugins/{plugin_key}) للمتابعة."
                ),
            )

        usage[plugin_key] = used + 1
        tenant.demo_usage = usage
        session.add(tenant)
        await session.commit()

    return Depends(_check_plugin_active)
