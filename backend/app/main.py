"""
app/main.py — FastAPI Application Gateway

Router mount map:
  /api/v1/auth/*         → system.router      (register, login, refresh, me)
  /api/v1/contacts/*     → contacts.router    (CRM: customers & suppliers)
  /api/v1/accounting/*   → accounting.router  (Chart of Accounts, Journal Entries)
  /api/v1/inventory/*    → inventory.router   (Items, Invoices with EventBus)
  /api/v1/purchases/*    → purchases.router   (Purchase Invoices)
  /api/v1/sales/*        → sales.router       (Sales Invoices)
  /api/v1/news/*         → news.router        (Internal Announcements)
  /api/v1/dashboard/*    → dashboard.router   (Real-time KPI Metrics)
  /api/v1/team/*         → team.router        (User/Team Management)
  /health                → inline             (infrastructure health check)

Middleware stack (applied in registration order, executes in reverse):
  1. CORSMiddleware       — Allow cross-origin requests (React/Next.js frontend)
  2. TenantMiddleware     — Decode JWT → set request.state.tenant_id/user_id/roles

Side-effect imports at module load:
  `import app.modules.accounting.events`
  This runs the @event_bus.subscribe decorators, registering handlers BEFORE
  any request is processed. Without this, published events have no listeners.

Startup sequence:
  1. Verify PostgreSQL connection
  2. Auto-create public schema tables (Tenant, User) — idempotent
  3. Verify Redis connection
  4. Log EventBus backend in use
  5. Server begins accepting requests
"""
from __future__ import annotations

import sys
import asyncio
if sys.platform == "win32":
    # Fix for asyncpg/greenlet random segmentation faults on Windows ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from opentelemetry import trace
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

# ── CRITICAL: Register EventBus handlers before first request ─────────────────
# This is a side-effect import. The module body runs @event_bus.subscribe(),
# registering handle_invoice_created and handle_payment_received.
# Remove this import → events are published but never processed.
import app.modules.accounting.events  # also registers consumers/events.py + consumers/purchasing_events.py
import app.modules.eta.events
import app.modules.inventory.events
import app.modules.logistics.events
import app.plugins.whatsapp.listeners
import app.plugins.recruitment.listeners
import app.plugins.travel.listeners
import app.plugins.hospitality.listeners
import app.plugins.rental.listeners
from app.core.config import settings
from app.core.db.database import TenantMiddleware, engine, redis_client
from app.core.observability.logging import setup_logging
from app.core.observability.middleware import ObservabilityMiddleware
from app.core.security.middleware import PayloadSizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.security.throttling import RateLimiterMiddleware

# Initialize structlog
setup_logging(json_logs=True, log_level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = structlog.get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown logic."""
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  Omni ERP Platform — Starting [%s]", settings.ENVIRONMENT.upper())
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── Step 1: PostgreSQL health check ───────────────────────────────────────
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ PostgreSQL connection verified")
    except Exception as exc:
        logger.critical("❌ PostgreSQL unreachable on startup: %s", exc)
        raise

    # ── Step 2: Ensure Alembic migrations are used instead of create_all ──────────
    logger.info("✅ Database connection ready. (Migrations should be run via Alembic)")

    # ── Step 3: Redis health check ────────────────────────────────────────────
    try:
        await redis_client.ping()
        logger.info("✅ Redis connection verified")
    except Exception as exc:
        logger.warning("⚠️  Redis unavailable (refresh tokens disabled): %s", exc)

    logger.info(
        "✅ EventBus handlers registered (backend=%s)", settings.EVENT_BUS_BACKEND,
    )
    logger.info("✅ Ready → http://0.0.0.0:8000/docs")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    yield  # ← Server accepts requests here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down Omni ERP...")
    await engine.dispose()
    await redis_client.aclose()
    logger.info("Connections closed. Goodbye.")


# ── Application Factory ───────────────────────────────────────────────────────

def create_application() -> FastAPI:
    """
    Build and configure the FastAPI application.

    Using a factory function (rather than module-level instantiation) allows
    tests to call `create_application()` with dependency overrides applied
    before the app is created.
    """
    _app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description=(
            "## Omni ERP — Multi-Tenant ERP & Trust Network Platform\n\n"
            "### 🚀 Quick Start\n"
            "1. `POST /api/v1/auth/register` — Register your company (no token needed)\n"
            "2. `POST /api/v1/auth/login` — Get JWT access + refresh tokens\n"
            "3. Click **Authorize** (🔒) → enter `Bearer <your_access_token>`\n\n"
            "### 📋 Core Flow Demo\n"
            "```\n"
            "POST /api/v1/contacts/          → Create a customer\n"
            "POST /api/v1/inventory/items    → Create an item (SKU)\n"
            "POST /api/v1/inventory/invoices → Create invoice\n"
            "                                  ↓ emits invoice.created event\n"
            "                                  ↓ accounting handler fires\n"
            "GET  /api/v1/accounting/journal-entries → See the auto-created journal entry\n"
            "GET  /api/v1/accounting/accounts/1200/balance → AR balance\n"
            "```\n\n"
            "### 🏗️ Architecture\n"
            "- **Multi-tenant**: Schema-per-tenant PostgreSQL isolation\n"
            "- **Double-entry**: Enforced at Pydantic + Service + DB trigger layers\n"
            "- **Event-driven**: Inventory ↔ Accounting decoupled via EventBus\n"
            "- **Neo4j-ready**: Contact models annotated for graph extraction\n"
        ),
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Observability Setup ───────────────────────────────────────────────────
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=1.0,
        )

    provider = TracerProvider()
    if settings.OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTLP_ENDPOINT)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(_app)

    Instrumentator().instrument(_app).expose(_app, endpoint="/metrics")

    # ── Middleware (Applied Bottom-Up: Last added executes first) ─────────────
    
    # 6. Executes 6th: Rate Limiting (Needs tenant_id from TenantMiddleware)
    _app.add_middleware(RateLimiterMiddleware, max_requests=300, window_seconds=60)
    
    # 5. Executes 5th: Tenant resolution (Decodes JWT -> sets tenant_id)
    _app.add_middleware(TenantMiddleware)
    
    # 4. Executes 4th: Observability (Generates trace_id and request_id)
    _app.add_middleware(ObservabilityMiddleware)
    
    # 3. Executes 3rd: Payload Size Limit (Drops huge requests early)
    _app.add_middleware(
        PayloadSizeLimitMiddleware, 
        whitelist_prefixes=["/api/v1/attachments"],
    )
    
    # 2. Executes 2nd: CORS (Handles preflight OPTIONS so they bypass auth)
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 1. Executes 1st: Security Headers (Wraps all responses)
    _app.add_middleware(SecurityHeadersMiddleware)

    # ── Global Exception Handlers ────────────────────────────────────────────
    # These catch anything that escapes the routers/services layer. They must
    # NOT swallow HTTPException/StarletteHTTPException/RequestValidationError —
    # those are intentional, user-facing responses (e.g. "لا يمكنك إغلاق وردية
    # كاشير آخر") and FastAPI/Starlette already has default handlers for them
    # registered before these run. Starlette's ExceptionMiddleware picks the
    # MOST SPECIFIC matching handler for the raised exception's type, so
    # registering handlers here for SQLAlchemyError and the base Exception
    # only ever fires for exceptions that aren't already handled elsewhere —
    # it never intercepts a deliberately-raised HTTPException.
    @_app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> ORJSONResponse:
        logger.error(
            "Unhandled database error",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "حدث خطأ غير متوقع. حاول مرة أخرى أو تواصل مع الدعم الفني."},
        )

    @_app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
        # Defensive: HTTPException/StarletteHTTPException/RequestValidationError
        # should never reach here (FastAPI's own handlers are more specific and
        # take precedence), but if any middleware ever re-raises one through a
        # path that bypasses that lookup, re-raise so it's handled correctly
        # rather than being masked as a generic 500.
        if isinstance(exc, (HTTPException, StarletteHTTPException, RequestValidationError)):
            raise exc

        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "حدث خطأ غير متوقع. حاول مرة أخرى أو تواصل مع الدعم الفني."},
        )

    # ── Routers ───────────────────────────────────────────────────────────────

    # 1. System / Auth — public schema (register, login, me)
    from app.modules.system.router import router as system_router
    _app.include_router(
        system_router,
        prefix=f"{settings.API_V1_PREFIX}/auth",
        tags=["System / Auth"],
    )

    # 2. Contacts CRM — tenant schema (customers, suppliers)
    from app.modules.contacts.router import router as contacts_router
    _app.include_router(
        contacts_router,
        prefix=f"{settings.API_V1_PREFIX}/contacts",
        tags=["Contacts"],
    )

    # 3. Accounting Core — tenant schema (Chart of Accounts, Journal Entries)
    from app.modules.accounting.router import router as accounting_router
    _app.include_router(
        accounting_router,
        prefix=f"{settings.API_V1_PREFIX}/accounting",
        tags=["Accounting"],
    )

    # 4. Inventory (modules/) — tenant schema (Items, Warehouses, Stock/Cost Layers)
    # Cut over from app.plugins.inventory (retired). Item no longer carries
    # price/cost/quantity_on_hand directly — see ItemVariant/StockLevel.
    from app.modules.inventory.router import router as inventory_router
    _app.include_router(
        inventory_router,
        prefix=f"{settings.API_V1_PREFIX}/inventory",
        tags=["Inventory"],
    )

    # 5. Purchasing (modules/) — tenant schema (Vendor Bills, Three-Way Match)
    # Cut over from app.plugins.purchases (retired). URL shape changed:
    # was /api/v1/purchases/invoices, now /api/v1/purchasing/bills.
    from app.modules.purchasing.router import router as purchasing_router
    _app.include_router(
        purchasing_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Purchasing"],
    )

    # 6. Sales (modules/) — tenant schema (Sales Invoices — order-based or ad-hoc)
    # Cut over from app.plugins.sales (retired). URL shape unchanged:
    # /api/v1/sales/invoices.
    from app.modules.sales.router import router as sales_router
    _app.include_router(
        sales_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Sales"],
    )

    # 7. News / Announcements — tenant schema
    # NOTE: models.py is an empty stub — will register when model is implemented
    try:
        from app.modules.news.router import router as news_router
        _app.include_router(
            news_router,
            prefix=f"{settings.API_V1_PREFIX}/news",
            tags=["News"],
        )
    except ImportError as exc:
        logger.warning("⚠️  News module skipped (models not yet implemented): %s", exc)

    # 8. Dashboard — tenant schema (real-time KPI metrics)
    from app.modules.dashboard.router import router as dashboard_router
    _app.include_router(
        dashboard_router,
        prefix=f"{settings.API_V1_PREFIX}/dashboard",
        tags=["Dashboard"],
    )

    # 9. Team / User Management — public schema (OWNER only)
    from app.modules.system.team_router import router as team_router
    _app.include_router(
        team_router,
        prefix=f"{settings.API_V1_PREFIX}/team",
        tags=["Team Management"],
    )

    # 10. ETA Compliance Webhook Callbacks — tenant schema
    from app.modules.eta.api.callbacks import router as eta_callbacks_router
    _app.include_router(
        eta_callbacks_router,
        tags=["ETA Callbacks"],
    )

    # 10b. ETA Compliance — tenant config, EGS code registry, document state (read/manage)
    from app.modules.eta.api.config import router as eta_config_router
    _app.include_router(
        eta_config_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["ETA E-Invoicing"],
    )

    # 10c. ETA Compliance — submission pipeline (build, sign, submit to ETA gateway)
    # Unblocked now that modules/sales + modules/inventory are the live,
    # provisioned Inventory/Sales/Purchasing implementation.
    from app.modules.eta.api.submissions import router as eta_submissions_router
    _app.include_router(
        eta_submissions_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["ETA E-Invoicing"],
    )

    # 11. Carrier Integration Webhooks — tenant schema (Bosta, Mylerz)
    from app.modules.logistics.api import webhooks_router as carrier_webhooks_router
    _app.include_router(
        carrier_webhooks_router,
        tags=["Carrier Webhooks"],
    )

    # 11b. Shipping Plugin — carrier account config + shipment/waybill creation.
    # Authenticated, tenant-facing, /api/v1 (unlike the bare-root webhook above).
    from app.modules.logistics.api import carriers_router as logistics_carriers_router
    from app.modules.logistics.api import shipments_router as logistics_shipments_router
    _app.include_router(
        logistics_carriers_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Logistics — Carrier Accounts"],
    )
    _app.include_router(
        logistics_shipments_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Logistics — Shipments"],
    )

    # 12. COD Settlements & Reconciliation — tenant schema (Phase 7c)
    from app.modules.finance.router import router as finance_router
    _app.include_router(
        finance_router,
        tags=["COD Settlements"],
    )

    # 13. Imports Cycle — tenant schema
    from app.modules.imports.router import router as imports_router
    _app.include_router(
        imports_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Imports"],
    )

    # 14. WhatsApp Webhooks — public plugin endpoints (bare root, Meta calls a fixed URL)
    try:
        from app.plugins.whatsapp.router import router as whatsapp_router
        _app.include_router(
            whatsapp_router,
            tags=["WhatsApp Webhook"],
        )
    except ImportError as exc:
        logger.warning("⚠️  WhatsApp plugin skipped: %s", exc)

    # 14b. WhatsApp Integration Config — authenticated, tenant-facing, /api/v1
    from app.plugins.whatsapp.api.config import router as whatsapp_config_router
    _app.include_router(
        whatsapp_config_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["WhatsApp Integration"],
    )

    # 15. Client Portal — self-service external API
    from app.modules.portal.router import router as portal_router
    _app.include_router(
        portal_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Client Portal"],
    )

    # 16. HR & Payroll
    from app.modules.hr.router import router as hr_router
    _app.include_router(
        hr_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["HR & Payroll"],
    )

    # 17. Generic Case / Process Engine
    from app.modules.cases.router import router as cases_router
    _app.include_router(
        cases_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Case Engine"],
    )

    # Plugin Marketplace access gate (app.core.dependencies.plugin_gate) —
    # applied ONLY to the four vertical routers below (18-21). Core modules
    # (auth, billing, inventory, sales, purchasing, cases, trust, eta,
    # approvals, pos, ...) are never given this dependency, so they are
    # structurally exempt rather than relying on an exclusion list.
    from app.core.dependencies.plugin_gate import require_plugin

    # 18. Recruitment Plugin
    from app.plugins.recruitment.api import router as recruitment_router
    _app.include_router(
        recruitment_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Recruitment Plugin"],
        dependencies=[require_plugin("recruitment")],
    )

    # 19. Travel & Tourism Plugin
    from app.plugins.travel.api import router as travel_router
    _app.include_router(
        travel_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Travel Plugin"],
        dependencies=[require_plugin("travel")],
    )

    # 20. Hospitality Plugin — Rooms
    from app.plugins.hospitality.api.rooms import router as hospitality_rooms_router
    _app.include_router(
        hospitality_rooms_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Hospitality Plugin"],
        dependencies=[require_plugin("hospitality")],
    )

    # 20b. Hospitality Plugin — Folio
    from app.plugins.hospitality.api.folio import router as hospitality_folio_router
    _app.include_router(
        hospitality_folio_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Hospitality Plugin"],
        dependencies=[require_plugin("hospitality")],
    )

    # 20c. Hospitality Plugin — Bootstrap
    from app.plugins.hospitality.api.bootstrap import router as hospitality_boot_router
    _app.include_router(
        hospitality_boot_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Hospitality Plugin"],
        dependencies=[require_plugin("hospitality")],
    )

    # 21. Vehicle Rental Plugin
    from app.plugins.rental.api.fleet import router as rental_fleet_router
    _app.include_router(
        rental_fleet_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Rental Plugin"],
        dependencies=[require_plugin("rental")],
    )

    from app.plugins.rental.api.inspection import router as rental_inspection_router
    _app.include_router(
        rental_inspection_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Rental Plugin"],
        dependencies=[require_plugin("rental")],
    )

    from app.plugins.rental.api.bootstrap import router as rental_boot_router
    _app.include_router(
        rental_boot_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Rental Plugin"],
        dependencies=[require_plugin("rental")],
    )

    # 22. Approval Engine — segregation-of-duties enforced approvals
    from app.modules.approvals.api import router as approvals_router
    _app.include_router(
        approvals_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Approvals"],
    )

    # 23. Trust Network — cross-tenant privacy-preserving reputation (public schema)
    from app.modules.trust.api import router as trust_router
    _app.include_router(
        trust_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Trust Network"],
    )

    # 24. Billing & Subscriptions — launch-blocking per Phase 8 (public schema)
    from app.modules.billing.api import router as billing_router
    _app.include_router(
        billing_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Billing"],
    )

    # 24b. Paymob payment webhook — public, bare root (Paymob calls one
    # fixed URL with no tenant context; see api_webhooks module docstring).
    from app.modules.billing.api_webhooks import router as billing_webhooks_router
    _app.include_router(
        billing_webhooks_router,
        tags=["Billing Webhook"],
    )

    # 25. Plugin Marketplace — toggles Tenant.active_plugins (public schema)
    from app.modules.system.api_plugins import router as plugins_router, packages_router
    _app.include_router(
        plugins_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Plugin Marketplace"],
    )
    _app.include_router(
        packages_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Plugin Marketplace"],
    )

    # 26. Point of Sale — built from scratch (Phase 6 gap); reuses the real
    # sales invoicing pipeline for checkout, tenant schema.
    from app.modules.pos.api import router as pos_router
    _app.include_router(
        pos_router,
        prefix=f"{settings.API_V1_PREFIX}",
        tags=["Point of Sale"],
    )

    # ── Infrastructure ────────────────────────────────────────────────────────
    @_app.get("/health", tags=["Infrastructure"], summary="Health check")
    async def health_check(response: Response) -> dict:
        """
        Returns server status. Does NOT require authentication.

        This used to unconditionally return {"status": "healthy"} with no
        actual check — orchestrators (k8s liveness/readiness probes, load
        balancer health checks) would keep routing traffic to a pod whose
        Postgres or Redis connection had died AFTER startup, since the only
        real connectivity check ran once in `lifespan()` at boot. This now
        does a real, cheap per-request check of both, so a mid-life outage
        actually flips the probe and gets the pod pulled out of rotation
        instead of silently 500ing on every real request.
        """
        db_ok = False
        redis_ok = False

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:
            logger.warning("Health check: PostgreSQL unreachable: %s", exc)

        try:
            await redis_client.ping()
            redis_ok = True
        except Exception as exc:
            logger.warning("Health check: Redis unreachable: %s", exc)

        # Redis is used for rate limiting / refresh tokens / the Redis event
        # bus backend — degraded-but-serving, not down, so it doesn't flip
        # the overall status on its own. Postgres is load-bearing for
        # everything; its failure means "unhealthy".
        overall_ok = db_ok
        response.status_code = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "healthy" if overall_ok else "unhealthy",
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0",
            "checks": {
                "database": "ok" if db_ok else "unreachable",
                "redis": "ok" if redis_ok else "unreachable",
            },
        }

    return _app


# Module-level app instance — used by uvicorn and test client
app = create_application()
