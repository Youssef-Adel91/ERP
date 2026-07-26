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

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from opentelemetry import trace
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
import app.modules.accounting.events
import app.plugins.inventory.events
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
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
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

    # 4. Inventory Plugin — tenant schema (Items, Invoices + EventBus trigger)
    from app.plugins.inventory.router import router as inventory_router
    _app.include_router(
        inventory_router,
        prefix=f"{settings.API_V1_PREFIX}/inventory",
        tags=["Inventory Plugin"],
    )

    # 5. Purchases Plugin — tenant schema (Purchase Invoices)
    # NOTE: models.py is an empty stub — will register when models are implemented
    try:
        from app.plugins.purchases.router import router as purchases_router
        _app.include_router(
            purchases_router,
            prefix=f"{settings.API_V1_PREFIX}/purchases",
            tags=["Purchases Plugin"],
        )
    except ImportError as exc:
        logger.warning("⚠️  Purchases plugin skipped (models not yet implemented): %s", exc)

    # 6. Sales Plugin — tenant schema (Sales Invoices)
    # NOTE: models.py is an empty stub — will register when models are implemented
    try:
        from app.plugins.sales.router import router as sales_router
        _app.include_router(
            sales_router,
            prefix=f"{settings.API_V1_PREFIX}/sales",
            tags=["Sales Plugin"],
        )
    except ImportError as exc:
        logger.warning("⚠️  Sales plugin skipped (models not yet implemented): %s", exc)

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

    # ── Infrastructure ────────────────────────────────────────────────────────
    @_app.get("/health", tags=["Infrastructure"], summary="Health check")
    async def health_check() -> dict:
        """Returns server status. Does NOT require authentication."""
        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0",
        }

    return _app


# Module-level app instance — used by uvicorn and test client
app = create_application()
