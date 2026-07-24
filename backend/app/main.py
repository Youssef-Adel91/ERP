"""
app/main.py — FastAPI Application Gateway

Router mount map:
  /api/v1/auth/*         → system.router      (register, login, refresh, me)
  /api/v1/contacts/*     → contacts.router    (CRM: customers & suppliers)
  /api/v1/accounting/*   → accounting.router  (Chart of Accounts, Journal Entries)
  /api/v1/inventory/*    → inventory.router   (Items, Invoices with EventBus)
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
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from sqlalchemy import text
from sqlmodel import SQLModel

from app.core.config import settings
from app.core.database import TenantMiddleware, engine, redis_client

# ── CRITICAL: Register EventBus handlers before first request ─────────────────
# This is a side-effect import. The module body runs @event_bus.subscribe(),
# registering handle_invoice_created and handle_payment_received.
# Remove this import → events are published but never processed.
import app.modules.accounting.events  # noqa: F401, E402

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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

    # ── Step 2: Auto-create public schema tables (idempotent) ─────────────────
    # Creates `public.tenants` and `public.users` if they don't exist.
    # In production with Alembic, these tables already exist — this is a no-op.
    try:
        from app.modules.system.models import Tenant, User

        public_tables = [Tenant.__table__, User.__table__]
        async with engine.begin() as conn:
            await conn.execute(text("SET search_path TO public"))
            await conn.run_sync(
                lambda c: SQLModel.metadata.create_all(c, tables=public_tables)
            )
        logger.info("✅ Public schema tables ready (tenants, users)")
    except Exception as exc:
        logger.error("⚠️  Public schema table creation failed: %s", exc)

    # ── Step 3: Redis health check ────────────────────────────────────────────
    try:
        await redis_client.ping()
        logger.info("✅ Redis connection verified")
    except Exception as exc:
        logger.warning("⚠️  Redis unavailable (refresh tokens disabled): %s", exc)

    logger.info(
        "✅ EventBus handlers registered (backend=%s)", settings.EVENT_BUS_BACKEND
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

    # ── Middleware (applied bottom-up — CORS wraps everything) ────────────────
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # TenantMiddleware must be INSIDE CORSMiddleware so OPTIONS preflight
    # requests bypass tenant resolution (they carry no Bearer token)
    _app.add_middleware(TenantMiddleware)

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
