"""
app/modules/system/api_plugins.py — Plugin Marketplace API (Packages + Individual Plugins)

Backs the "سوق الإضافات" (Plugin Marketplace) frontend gallery.

Honest note on scope: the codebase has a dormant `Plugin`/`TenantPlugin`
pair of public-schema tables (app.modules.system.models) that were never
provisioned or wired to any API — the same "designed but dormant" pattern
found earlier in this project for Trust Network's original schema. Standing
those up would mean another Alembic migration + a plugin registry seed for
no functional gain over what already exists and is live today: `Tenant.
active_plugins` (a JSON string list column on the already-provisioned
`public.tenants` table). This router reads/writes that field directly.

Also honest: this endpoint does NOT currently gate access to the vertical
plugin routers themselves (hospitality/rental/travel/recruitment routers in
app.plugins.* are mounted unconditionally in main.py, independent of this
flag). Toggling here persists real tenant-level intent and is what the
marketplace UI reflects, but enforcing it as an actual feature gate on the
routers is a separate, not-yet-done piece of work (tracked, to be done as
part of final polish per explicit instruction).

Two-tier model (per explicit product decision):
  - Packages: a vertical bundle sold/installed as one unit for convenience
    (e.g. "Tourism & Labor Export" = Travel + Recruitment together).
    Installing a package activates every plugin inside it in one action.
  - Individual plugins: any single plugin — whether or not it's part of a
    package — can still be disabled on its own, AS LONG AS doing so doesn't
    break another currently-active plugin that depends on it. Verified via
    a full cross-plugin import grep (app/plugins/{hospitality,rental,
    travel,recruitment,whatsapp}) that none of the 5 shipped plugins import
    from one another today, so `depends_on` is empty for all of them right
    now — the dependency check below is a real, enforced safety net, just
    one that has nothing to block yet. If a future plugin genuinely depends
    on another, add it to `depends_on` and this logic protects it for free.
"""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.core.db.database import tenant_session
from app.core.dependencies.plugin_gate import DEMO_OPERATION_LIMIT
from app.modules.system.dependencies import CurrentUser, require_roles
from app.modules.system.models import Tenant

router = APIRouter(prefix="/plugins", tags=["Plugin Marketplace"])
packages_router = APIRouter(prefix="/packages", tags=["Plugin Marketplace"])


# Static catalogue of the vertical plugins that actually exist under app/plugins/.
# Kept in code (not DB) deliberately — this is a fixed set of verticals we ship,
# not a dynamic third-party plugin ecosystem.
PLUGIN_CATALOGUE = [
    {
        "key": "hospitality",
        "name_ar": "الفنادق والضيافة",
        "description_ar": "إدارة الغرف والحجوزات والفواتير الفندقية (Folio).",
        "depends_on": [],
        "video_url": None,
    },
    {
        "key": "rental",
        "name_ar": "تأجير المركبات",
        "description_ar": "إدارة أسطول التأجير، الفحص، والحجز.",
        "depends_on": [],
        "video_url": None,
    },
    {
        "key": "travel",
        "name_ar": "السياحة والسفر",
        "description_ar": "إدارة باقات السفر وحجوزات العملاء.",
        "depends_on": [],
        "video_url": None,
    },
    {
        "key": "recruitment",
        "name_ar": "التوظيف والاستقدام",
        "description_ar": "إدارة طلبات التوظيف والمرشحين.",
        "depends_on": [],
        "video_url": None,
    },
    {
        "key": "whatsapp",
        "name_ar": "تكامل واتساب",
        "description_ar": "إشعارات الطلبات والفواتير عبر واتساب.",
        "depends_on": [],
        "video_url": None,
    },
]
PLUGIN_KEYS = {p["key"] for p in PLUGIN_CATALOGUE}

# Vertical bundles. `plugin_keys` must all exist in PLUGIN_CATALOGUE.
PACKAGE_CATALOGUE = [
    {
        "key": "tourism_labor_export",
        "name_ar": "باقة السياحة وتصدير العمالة",
        "description_ar": "كل ما يحتاجه نشاط سياحة وسفر ومكتب استقدام/تصدير عمالة في مكان واحد.",
        "plugin_keys": ["travel", "recruitment"],
    },
    {
        "key": "hospitality_and_fleet",
        "name_ar": "باقة الضيافة وتأجير المركبات",
        "description_ar": "إدارة الفنادق والغرف مع أسطول تأجير المركبات معًا — لمقدمي الخدمات السياحية المتكاملة.",
        "plugin_keys": ["hospitality", "rental"],
    },
]


class PluginOut(BaseModel):
    key: str
    name_ar: str
    description_ar: str
    is_active: bool
    is_demo: bool = False  # tenant is trying this plugin free, via onboarding
    video_url: str | None = None
    package_key: str | None = None  # which package (if any) this plugin belongs to
    demo_operations_used: int = 0
    demo_operation_limit: int = DEMO_OPERATION_LIMIT


class PluginToggleIn(BaseModel):
    is_active: bool


class PackageOut(BaseModel):
    key: str
    name_ar: str
    description_ar: str
    plugin_keys: list[str]
    is_active: bool       # every plugin in the bundle is active
    is_partial: bool      # some, but not all, plugins in the bundle are active


def _package_for_plugin(plugin_key: str) -> str | None:
    for pkg in PACKAGE_CATALOGUE:
        if plugin_key in pkg["plugin_keys"]:
            return pkg["key"]
    return None


def _dependents_blocking_disable(plugin_key: str, active: set[str]) -> list[str]:
    """Returns the keys of any currently-active plugins that depend on plugin_key."""
    return [
        p["key"]
        for p in PLUGIN_CATALOGUE
        if p["key"] in active and plugin_key in p.get("depends_on", [])
    ]


async def _run_plugin_bootstrap(plugin_key: str, tenant_id) -> None:
    """
    Idempotently injects the plugin's CaseType into the Case Engine right
    when it's activated from the marketplace.

    WHY THIS EXISTS: before this, activating a plugin here only flipped
    `Tenant.active_plugins` (a public-schema flag) — it never called the
    plugin's own `/​<key>/bootstrap` endpoint (e.g.
    app.plugins.travel.bootstrap.bootstrap_travel_case_type), which is what
    actually inserts the CaseType row the plugin's pages query for. The
    result: every plugin page showed "غير مفعّل بعد" (not activated) right
    after a real activation, until someone manually hit the bootstrap
    endpoint — confirmed live while testing the Travel vertical. Each
    bootstrap_*_case_type() function is idempotent (checks for an existing
    CaseType by `code` first), so calling it here on every activation is
    safe even if it's already been bootstrapped before.
    Plugins with no CaseType-based data model (e.g. whatsapp) simply have
    no entry in this registry and are silently skipped.
    """
    bootstrap_fn = None
    if plugin_key == "travel":
        from app.plugins.travel.bootstrap import bootstrap_travel_case_type as bootstrap_fn
    elif plugin_key == "rental":
        from app.plugins.rental.bootstrap import bootstrap_rental_case_type as bootstrap_fn
    elif plugin_key == "hospitality":
        from app.plugins.hospitality.bootstrap import bootstrap_hospitality_case_type as bootstrap_fn
    elif plugin_key == "recruitment":
        from app.plugins.recruitment.bootstrap import bootstrap_recruitment_case_type as bootstrap_fn

    if bootstrap_fn is None:
        return

    async with tenant_session(tenant_id) as tsession:
        await bootstrap_fn(tsession)


# ── Individual plugins ─────────────────────────────────────────────────────────


@router.get("", response_model=list[PluginOut])
async def list_plugins(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    tenant = await session.get(Tenant, current_user.tenant_id)
    active = set(tenant.active_plugins if tenant else [])
    demo = set(tenant.demo_plugins if tenant else [])
    usage = tenant.demo_usage if tenant else {}
    return [
        PluginOut(
            key=p["key"],
            name_ar=p["name_ar"],
            description_ar=p["description_ar"],
            is_active=p["key"] in active,
            is_demo=p["key"] in demo and p["key"] not in active,
            video_url=p.get("video_url"),
            package_key=_package_for_plugin(p["key"]),
            demo_operations_used=(usage or {}).get(p["key"], 0),
        )
        for p in PLUGIN_CATALOGUE
    ]


@router.post("/{plugin_key}/demo", response_model=PluginOut)
async def try_plugin_demo(
    plugin_key: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Free onboarding trial — grants router access to the plugin (see
    require_plugin() in app/core/dependencies/plugin_gate.py) without
    touching `active_plugins` (billing/marketplace state stays untouched).
    Reads are unlimited; mutating requests (create/update/delete) are capped
    at DEMO_OPERATION_LIMIT and tracked in `Tenant.demo_usage`. Idempotent.
    Any authenticated tenant member can start a demo for their own tenant —
    no OWNER/ADMIN restriction, unlike the real paid toggle, since nothing
    is being purchased.
    """
    catalogue_entry = next((p for p in PLUGIN_CATALOGUE if p["key"] == plugin_key), None)
    if not catalogue_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown plugin '{plugin_key}'.")

    tenant = await session.get(Tenant, current_user.tenant_id)
    demo = list(tenant.demo_plugins or [])
    newly_activated = plugin_key not in demo
    if newly_activated:
        demo.append(plugin_key)
        tenant.demo_plugins = demo
        session.add(tenant)
        await session.commit()

    if newly_activated:
        await _run_plugin_bootstrap(plugin_key, current_user.tenant_id)

    active = set(tenant.active_plugins or [])
    return PluginOut(
        key=catalogue_entry["key"],
        name_ar=catalogue_entry["name_ar"],
        description_ar=catalogue_entry["description_ar"],
        is_active=plugin_key in active,
        is_demo=plugin_key not in active,
        video_url=catalogue_entry.get("video_url"),
        package_key=_package_for_plugin(plugin_key),
        demo_operations_used=(tenant.demo_usage or {}).get(plugin_key, 0),
    )


@router.put(
    "/{plugin_key}",
    response_model=PluginOut,
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def toggle_plugin(
    plugin_key: str,
    data: PluginToggleIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    catalogue_entry = next((p for p in PLUGIN_CATALOGUE if p["key"] == plugin_key), None)
    if not catalogue_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown plugin '{plugin_key}'.")

    tenant = await session.get(Tenant, current_user.tenant_id)
    active = list(tenant.active_plugins or [])

    if not data.is_active and plugin_key in active:
        blockers = _dependents_blocking_disable(plugin_key, set(active))
        if blockers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"لا يمكن إلغاء تفعيل '{plugin_key}' لأن الإضافات التالية تعتمد عليها: {', '.join(blockers)}.",
            )

    newly_activated = data.is_active and plugin_key not in active

    if data.is_active and plugin_key not in active:
        active.append(plugin_key)
    elif not data.is_active and plugin_key in active:
        active.remove(plugin_key)

    tenant.active_plugins = active
    session.add(tenant)
    await session.commit()

    if newly_activated:
        await _run_plugin_bootstrap(plugin_key, current_user.tenant_id)

    return PluginOut(
        key=catalogue_entry["key"],
        name_ar=catalogue_entry["name_ar"],
        description_ar=catalogue_entry["description_ar"],
        is_active=data.is_active,
        package_key=_package_for_plugin(plugin_key),
    )


# ── Packages (bundles installed/uninstalled as one unit) ──────────────────────


@packages_router.get("", response_model=list[PackageOut])
async def list_packages(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    tenant = await session.get(Tenant, current_user.tenant_id)
    active = set(tenant.active_plugins if tenant else [])
    out = []
    for pkg in PACKAGE_CATALOGUE:
        active_count = sum(1 for k in pkg["plugin_keys"] if k in active)
        out.append(
            PackageOut(
                key=pkg["key"],
                name_ar=pkg["name_ar"],
                description_ar=pkg["description_ar"],
                plugin_keys=pkg["plugin_keys"],
                is_active=active_count == len(pkg["plugin_keys"]),
                is_partial=0 < active_count < len(pkg["plugin_keys"]),
            )
        )
    return out


@packages_router.post(
    "/{package_key}/install",
    response_model=PackageOut,
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def install_package(
    package_key: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """Activates every plugin in the bundle at once (buying the package)."""
    pkg = next((p for p in PACKAGE_CATALOGUE if p["key"] == package_key), None)
    if not pkg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown package '{package_key}'.")

    tenant = await session.get(Tenant, current_user.tenant_id)
    active = list(tenant.active_plugins or [])
    newly_activated = [k for k in pkg["plugin_keys"] if k not in active]
    for plugin_key in pkg["plugin_keys"]:
        if plugin_key not in active:
            active.append(plugin_key)

    tenant.active_plugins = active
    session.add(tenant)
    await session.commit()

    for plugin_key in newly_activated:
        await _run_plugin_bootstrap(plugin_key, current_user.tenant_id)

    return PackageOut(
        key=pkg["key"], name_ar=pkg["name_ar"], description_ar=pkg["description_ar"],
        plugin_keys=pkg["plugin_keys"], is_active=True, is_partial=False,
    )


@packages_router.post(
    "/{package_key}/uninstall",
    response_model=PackageOut,
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def uninstall_package(
    package_key: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Deactivates every plugin in the bundle at once — a convenience action.
    Individual plugins can still be turned off one at a time via
    PUT /plugins/{key} (per the explicit "buy together, disable
    individually if safe" product decision); this endpoint is the
    all-at-once counterpart to /install, honoring the same dependency
    safety check per plugin.
    """
    pkg = next((p for p in PACKAGE_CATALOGUE if p["key"] == package_key), None)
    if not pkg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown package '{package_key}'.")

    tenant = await session.get(Tenant, current_user.tenant_id)
    active = list(tenant.active_plugins or [])
    active_set = set(active)

    blocked: list[str] = []
    for plugin_key in pkg["plugin_keys"]:
        if plugin_key in active_set:
            blockers = _dependents_blocking_disable(plugin_key, active_set - {plugin_key})
            if blockers:
                blocked.append(plugin_key)

    if blocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"لا يمكن إلغاء تثبيت الباقة كاملة — الإضافات التالية معتمَد عليها من إضافات أخرى فعّالة: {', '.join(blocked)}.",
        )

    active = [k for k in active if k not in pkg["plugin_keys"]]
    tenant.active_plugins = active
    session.add(tenant)
    await session.commit()

    return PackageOut(
        key=pkg["key"], name_ar=pkg["name_ar"], description_ar=pkg["description_ar"],
        plugin_keys=pkg["plugin_keys"], is_active=False, is_partial=False,
    )
