"""
app/core/db/database.py — Async Database Engine & Multi-Tenant Session Management

Architecture:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Every HTTP request goes through TenantMiddleware               │
  │    → decodes JWT → sets request.state.tenant_id                 │
  │                                                                  │
  │  get_tenant_db() dependency picks up tenant_id and executes:    │
  │    SET search_path TO tenant_{id}, public                       │
  │                                                                  │
  │  All ORM queries in that session automatically target the        │
  │  correct tenant schema. ZERO extra filtering needed.             │
  └─────────────────────────────────────────────────────────────────┘

Schema Provisioning (provision_tenant_schema):
  Called ONCE when a new tenant registers. Steps:
  1. CREATE SCHEMA tenant_{id}
  2. Run the real `alembic/tenant/` migration chain against the new schema
     (TenantMigrationOrchestrator._migrate_tenant) — creates every tenant
     table AND stamps alembic_version, so future tenant migrations apply
     cleanly. NOT create_all() — see _provision_tenant_schema_internal's
     docstring for why that mattered.
  3. Seeds default Chart of Accounts (system accounts required for events)
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings
from app.core.db.context import current_session, schema_for
from app.core.security.security import decode_token

logger = logging.getLogger(__name__)

# ── Async Engine ──────────────────────────────────────────────────────────────

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine_kwargs = {
    "echo": settings.DEBUG,
    "future": True,
    "json_serializer": json.dumps,
    "json_deserializer": json.loads,
}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "connect_args": {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    })

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Redis ─────────────────────────────────────────────────────────────────────

redis_client: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=False,
)


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency — yields the shared Redis client."""
    yield redis_client


# ── Session Context Managers ──────────────────────────────────────────────────


@asynccontextmanager
async def public_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an async session without any schema translation.
    Defaults to the public schema for global models.
    """
    async with AsyncSessionLocal() as session:
        token = current_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            current_session.reset(token)
            await session.close()


@asynccontextmanager
async def tenant_session(tenant_id: UUID | str) -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an async session with schema_translate_map applied.
    All models with {"schema": "tenant"} will be routed to the tenant's schema.
    """
    schema = schema_for(tenant_id)
    async with AsyncSessionLocal() as session:
        # Apply translation map at the connection level for this session
        await session.connection(
            execution_options={"schema_translate_map": {"tenant": schema}},
        )
        token = current_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            current_session.reset(token)
            await session.close()


# ── Session Dependencies (FastAPI) ────────────────────────────────────────────


async def get_public_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a public session.
    Use ONLY in the system module (auth, tenant management).
    """
    async with public_session() as session:
        yield session


async def get_tenant_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a tenant session.
    Reads request.state.tenant_id set by TenantMiddleware.
    """
    tenant_id: str | None = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required — could not resolve tenant context.",
        )

    async with tenant_session(tenant_id) as session:
        yield session


# ── Tenant Schema Provisioning ────────────────────────────────────────────────


def _schema_name(tenant_id: str) -> str:
    """Convert a UUID string to a valid PostgreSQL schema name."""
    return schema_for(tenant_id)


async def _provision_tenant_schema_internal(tenant_id: str, seed_coa: bool = True) -> str:
    """
    One-time setup for a new tenant. Performs three operations atomically:

    1. CREATE SCHEMA tenant_{id}       — Isolated namespace for this merchant
    2. create_all(tenant_tables)       — All domain tables (accounting, contacts…)
    3. Seed default Chart of Accounts  — System accounts needed by event handlers

    Returns the created schema name.

    This function uses `engine.begin()` (raw connection, not a session) because
    DDL operations (CREATE SCHEMA / CREATE TABLE) cannot run inside a transaction
    that also holds DML. Using a separate connection avoids that conflict.
    """
    from app.modules.accounting.models import (
        DEFAULT_ACCOUNTS,
        Account,
        JournalEntry,
        TransactionLine,
    )
    from app.modules.contacts.models import Contact
    from app.modules.finance.models import (
        CarrierReceivableSnapshot,
        CarrierSettlement,
        SettlementLine,
    )
    from app.modules.logistics.models import (
        CarrierAccount,
        CarrierWebhookEvent,
        Shipment,
        ShipmentEvent,
    )
    from app.modules.hr.models.core import Employee, Payslip
    from app.modules.cases.models.core import (
        CaseType, Resource, Case, CaseContact, CaseStageHistory
    )
    from app.modules.cases.models.vendor import Vendor, VendorRateCard
    # WhatsAppTenantConfig moved to public schema (see its module docstring) —
    # no longer part of tenant provisioning, intentionally not imported here.
    from app.plugins.recruitment.models.job_orders import JobOrder, JobOrderCase
    from app.plugins.hospitality.models.folio import FolioItem
    from app.plugins.rental.models.inspection import VehicleInspection
    from app.modules.finance.models.cheques import Cheque
    from app.modules.news.models import Announcement
    from app.modules.imports.models.core import ImportDossier, ImportExpense
    from app.modules.approvals.models.core import ApprovalRule, ApprovalRequest, ApprovalDecision
    from app.modules.eta.models.core import EtaTenantConfig, EtaDocument, EtaSubmission
    from app.modules.eta.models.codes import EgsCode

    # Inventory/Sales/Purchasing — cut over from app.plugins.{inventory,sales,
    # purchases} to the enterprise-grade app.modules.{inventory,sales,
    # purchasing} implementation (landed costs, serial/lot tracking, cost
    # layers, three-way match). The plugins/ tables (items, invoices,
    # invoice_lines, sales_invoices, sales_invoice_lines, purchase_invoices,
    # purchase_invoice_lines) are retired — see the cutover migration script
    # (scripts/cutover_plugins_to_modules.py) for dropping them from any
    # already-provisioned dev tenant.
    from app.modules.inventory.models.core import (
        Warehouse, Item, UnitOfMeasure, ItemVariant, ItemBarcode,
        Batch, SerialNumber, StockLevel, CostLayer, StockMovement, CostConsumption,
    )
    from app.modules.inventory.models.pricing import PriceList, PriceListRule
    from app.modules.inventory.models.reorder import StockReorderRule
    from app.modules.inventory.models.stock_take import StockTake, StockTakeLine
    from app.modules.inventory.models.transfer import StockTransfer, StockTransferLine
    from app.modules.sales.models.core import SalesOrder, SalesOrderLine
    from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceLine
    from app.modules.sales.models.returns import SalesReturn, SalesReturnLine
    from app.modules.sales.models.recurring import RecurringInvoiceProfile
    from app.modules.purchasing.models.core import (
        PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
    )
    from app.modules.purchasing.models.billing import VendorBill, VendorBillLine, ThreeWayMatchResult
    from app.modules.purchasing.models.landed_cost import (
        ImportShipment, LandedCostLine, LandedCostAllocation,
    )
    from app.modules.purchasing.models.payments import SupplierPayment, PaymentAllocation
    from app.modules.pos.models import CashShift, PosSale

    schema = schema_for(tenant_id)

    # Tables that belong inside the tenant schema.
    # ORDER IS CRITICAL — referenced tables must precede tables with FKs:
    #   Contact  must come before Invoice   (Invoice.contact_id → contacts.id)
    #   CarrierSettlement must come before SettlementLine
    tenant_tables = [
        Account.__table__,
        JournalEntry.__table__,
        TransactionLine.__table__,
        Contact.__table__,
        CarrierAccount.__table__,
        Shipment.__table__,
        ShipmentEvent.__table__,
        CarrierWebhookEvent.__table__,
        CarrierSettlement.__table__,
        SettlementLine.__table__,
        CarrierReceivableSnapshot.__table__,
        Employee.__table__,
        Payslip.__table__,
        # Case Engine — depends on contacts
        CaseType.__table__,
        Resource.__table__,
        Case.__table__,
        CaseContact.__table__,
        CaseStageHistory.__table__,
        # Vendor Rate Cards — depends on nothing but is used by Case Engine
        # verticals (Travel/Recruitment services[] line items)
        Vendor.__table__,
        VendorRateCard.__table__,       # FK → case_vendors
        # WhatsApp Integration table lives in public schema now — see
        # app.plugins.whatsapp.models docstring — not listed here.
        # Recruitment Plugin — depends on cases and contacts
        JobOrder.__table__,
        JobOrderCase.__table__,
        # Hospitality Plugin
        FolioItem.__table__,
        # Rental Plugin
        VehicleInspection.__table__,
        # Finance — Cheques (depends on contacts; invoice_id/transaction_id are
        # unconstrained UUID columns, no FK, so no extra ordering requirement)
        Cheque.__table__,

        # ── Inventory (modules/) — item_id/warehouse_id/batch_id/serial_id
        # columns throughout this set are unconstrained UUIDs (no enforced FK
        # in the source models), so within-inventory ordering isn't DB-critical,
        # but Warehouse/Item first keeps intent readable.
        Warehouse.__table__,
        Item.__table__,
        UnitOfMeasure.__table__,
        ItemVariant.__table__,
        ItemBarcode.__table__,
        Batch.__table__,
        SerialNumber.__table__,
        StockLevel.__table__,
        CostLayer.__table__,
        StockMovement.__table__,
        CostConsumption.__table__,
        PriceList.__table__,
        PriceListRule.__table__,
        StockReorderRule.__table__,
        StockTake.__table__,
        StockTakeLine.__table__,
        StockTransfer.__table__,
        StockTransferLine.__table__,

        # ── Sales (modules/) — SalesOrderLine/SalesInvoice/SalesReturn* carry
        # real enforced FKs, order matters here.
        SalesOrder.__table__,
        SalesOrderLine.__table__,          # FK → sales_orders
        SalesInvoice.__table__,            # FK → sales_orders (nullable, ad-hoc allowed)
        SalesInvoiceLine.__table__,        # FK → sales_invoices
        SalesReturn.__table__,             # FK → sales_orders (nullable), sales_invoices ×2
        SalesReturnLine.__table__,         # FK → sales_returns, sales_invoice_lines
        RecurringInvoiceProfile.__table__,

        # ── Purchasing (modules/) — real enforced FK chain: PO → PO Line,
        # PO → GRN → GRN Line, GRN Line → Vendor Bill Line (via LandedCostAllocation),
        # Vendor Bill → Vendor Bill Line, Vendor Bill → Payment Allocation.
        PurchaseOrder.__table__,
        PurchaseOrderLine.__table__,       # FK → purchase_orders
        GoodsReceipt.__table__,            # FK → purchase_orders (nullable)
        GoodsReceiptLine.__table__,        # FK → goods_receipts, purchase_order_lines (nullable)
        VendorBill.__table__,
        VendorBillLine.__table__,          # FK → vendor_bills
        ThreeWayMatchResult.__table__,
        ImportShipment.__table__,
        LandedCostLine.__table__,          # FK → import_shipments
        LandedCostAllocation.__table__,    # FK → landed_cost_lines, goods_receipt_lines
        SupplierPayment.__table__,
        PaymentAllocation.__table__,       # FK → supplier_payments, vendor_bills
        # POS — CashShift before PosSale (PosSale.shift_id FK), and both
        # after SalesInvoice above (PosSale.invoice_id FK).
        CashShift.__table__,
        PosSale.__table__,
        # News / Announcements — no FK dependencies
        Announcement.__table__,
        # Imports — depends on contacts (supplier_id has no FK constraint)
        ImportDossier.__table__,
        ImportExpense.__table__,
        # Approval Engine — no FK dependencies on the above (document_id is an
        # unconstrained UUID; requests can reference documents in any module)
        ApprovalRule.__table__,
        ApprovalRequest.__table__,
        ApprovalDecision.__table__,
        # ETA E-Invoicing — no FK dependencies on the above (item_id/document_id
        # are unconstrained UUID columns, safe regardless of which Inventory/
        # Sales table implementation is eventually chosen)
        EtaTenantConfig.__table__,
        EgsCode.__table__,
        EtaDocument.__table__,
        EtaSubmission.__table__,
    ]

    # ── Step 1 & 2: Create schema + tables ────────────────────────────────────
    # NOTE: tables are now created by running the real `alembic/tenant/`
    # migration chain (via TenantMigrationOrchestrator._migrate_tenant),
    # NOT create_all(). This closes the "Alembic tenant migrations bypassed
    # by create_all" gap: create_all only ever reflects *current* model
    # state and never stamps alembic_version, so a schema provisioned that
    # way can never safely receive a FUTURE tenant migration (it would try
    # to recreate tables that already exist). Running `alembic upgrade
    # head` instead both creates the tables AND leaves the schema at a
    # known, re-migratable revision. It's also idempotent — running it
    # again against an already-migrated schema (e.g.
    # scripts/cutover_plugins_to_modules.py's re-provisioning step) is a
    # no-op, same as create_all's IF NOT EXISTS semantics were.
    #
    # `tenant_tables` above is now unused for table creation but is kept as
    # living documentation of what belongs in the tenant schema, and as a
    # safety net: if it's ever missing a model that IS in a migration (or
    # vice versa), that's a signal the two have drifted and need attention.
    async with engine.begin() as conn:
        # CREATE SCHEMA (idempotent) — must exist before alembic can create
        # its own alembic_version table inside it.
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    from app.core.tenancy.migrations import TenantMigrationOrchestrator
    orchestrator = TenantMigrationOrchestrator()
    await orchestrator._migrate_tenant(schema)

    # ── Step 3: Seed default Chart of Accounts ────────────────────────────────
    # Each new tenant gets the same baseline chart, ready for event handlers.
    # NOT idempotent (Account.code is unique but there's no existence check
    # before insert) — only run for a genuinely new tenant. Callers doing a
    # table-creation-only re-run against an already-provisioned tenant (e.g.
    # scripts/cutover_plugins_to_modules.py, which re-runs this to create the
    # new modules/ tables on an existing tenant) must pass seed_coa=False or
    # this will raise a unique-constraint violation on re-seeding.
    if seed_coa:
        async with tenant_session(tenant_id) as session:
            for acct_data in DEFAULT_ACCOUNTS:
                account = Account(
                    code=acct_data["code"],
                    name=acct_data["name"],
                    name_ar=acct_data.get("name_ar"),
                    account_type=acct_data["type"],
                    is_system=acct_data.get("is_system", False),
                )
                session.add(account)

        logger.info(
            "✅ Tenant schema '%s' provisioned with %d default accounts.",
            schema,
            len(DEFAULT_ACCOUNTS),
        )
    else:
        logger.info(
            "✅ Tenant schema '%s' tables created/verified (COA seeding skipped).",
            schema,
        )
    return schema


async def provision_tenant_schema(tenant_id: str) -> str:
    """
    Wrapper to run the actual provisioning logic in a separate process to avoid
    Windows ProactorEventLoop + greenlet crashes inside ASGI processes.
    We use a standard threading.Thread and subprocess to fully decouple it.
    """
    import sys
    import threading
    import subprocess
    
    def _run_worker():
        script = f"""
import asyncio
import logging
logging.basicConfig(level=logging.INFO)
from app.core.db.database import _provision_tenant_schema_internal
asyncio.run(_provision_tenant_schema_internal('{tenant_id}'))
"""
        try:
            # Fully detach the subprocess so it does not tear down Uvicorn's console handles when it exits
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            
            subprocess.Popen(
                [sys.executable, "-c", script], 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags
            )
            logger.info("✅ Background provisioning process launched detached.")
        except Exception as exc:
            logger.error("❌ Background provisioning process failed: %s", exc)

    thread = threading.Thread(target=_run_worker, daemon=True)
    thread.start()
    
    return f"tenant_{tenant_id.replace('-', '_')}"

if __name__ == "__main__":
    import asyncio
    import sys
    if len(sys.argv) > 1:
        asyncio.run(_provision_tenant_schema_internal(sys.argv[1]))


async def drop_tenant_schema(tenant_id: str) -> None:
    """
    Permanently remove a tenant's schema. IRREVERSIBLE.
    Only callable from an explicit account-deletion workflow with confirmation.
    """
    schema = _schema_name(tenant_id)
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    logger.warning("⚠️  Dropped tenant schema: %s", schema)


# ── Tenant Resolution Middleware ──────────────────────────────────────────────

# Paths that skip tenant resolution entirely (auth + infra endpoints)
_BYPASS_PATHS = {
    "/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico", "/metrics",
    # Meta's WhatsApp webhook (verification GET + inbound POST). Meta calls
    # this one fixed global URL directly — it never sends a Bearer token or
    # X-Tenant-ID header (there IS no tenant context yet; resolving
    # phone_number_id -> tenant_id is exactly what the handler itself does,
    # against the public WhatsAppTenantConfig table — see
    # app.plugins.whatsapp.api.webhooks). Authenticity is instead verified
    # via hub.verify_token (GET) / X-Hub-Signature-256 HMAC (POST), both
    # checked inside the handler. Without this bypass entry the route is
    # unreachable in practice — TenantMiddleware 401s it before the request
    # ever reaches app.plugins.whatsapp.api.webhooks.
    "/webhooks/whatsapp",
    # Paymob's payment transaction webhook — same bare-root/bypass pattern.
    # Paymob calls one fixed URL (configured in their dashboard) with no
    # tenant context; app.modules.billing.api_webhooks resolves the tenant
    # itself via PaymentAttempt -> SubscriptionInvoice -> Subscription
    # AFTER verifying Paymob's HMAC-SHA512 signature. Without this entry
    # the route is unreachable — same 401-before-the-handler problem fixed
    # for WhatsApp and the carrier webhooks earlier this session.
    "/webhooks/billing/paymob",
    # Egyptian Tax Authority (ETA) asynchronous document-status callback —
    # same bare-root/bypass pattern as the others above. ETA calls one
    # fixed URL with no Bearer token or tenant context.
    # app.modules.eta.api.callbacks resolves the owning tenant itself by
    # matching the payload's submission/document identifier against real
    # EtaSubmission/EtaDocument rows (never trusts a client-supplied
    # tenant hint) — see that module's docstring. Without this bypass
    # entry the route is unreachable, same as the previously-fixed
    # WhatsApp/Paymob/carrier webhooks.
    "/notifications/documents",
}
_BYPASS_PREFIXES = (
    "/api/v1/system/auth/",
    "/api/v1/system/tenants/register",
    "/api/v1/auth/",            # The /api/v1/auth/register shortcut
    "/api/v1/portal/",          # Client Portal endpoints (self-managed auth)
    # Carrier (Bosta/Mylerz) status webhooks — same category as the
    # WhatsApp bypass above: carriers call one fixed URL per carrier code
    # with no Bearer token. app.modules.logistics.api.webhooks resolves
    # the tenant itself (from a claimed tenant_id) and, critically, does
    # NOT trust that claim until it verifies the request against that
    # tenant's own real webhook secret — see that module's docstring for
    # the previously-hardcoded-empty-secret bug this also fixes.
    "/api/v1/webhooks/carriers/",
)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Extracts tenant context from every authenticated request.

    Resolution order:
      1. `Authorization: Bearer <JWT>` → decoded to get tenant_id
      2. `X-Tenant-ID` header (service-to-service, internal use)
      3. Request is on a bypass path → tenant_id = None (allowed)
      4. No context found → 401

    Sets request.state.tenant_id, .current_user_id, .current_user_roles
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Bypass public / auth routes
        if request.url.path in _BYPASS_PATHS or any(
            request.url.path.startswith(p) for p in _BYPASS_PREFIXES
        ):
            request.state.tenant_id = None
            request.state.current_user_id = None
            request.state.current_user_roles = []
            return await call_next(request)

        # Strategy 1 — JWT Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                payload = decode_token(token)
                request.state.tenant_id = payload.tenant_id
                request.state.current_user_id = payload.sub
                request.state.current_user_roles = payload.roles
                return await call_next(request)
            except JWTError:
                return Response(
                    content='{"detail":"Invalid or expired token."}',
                    status_code=401,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # Strategy 2 — X-Tenant-ID header (internal / testing ONLY).
        #
        # This grants full tenant-schema access with current_user_id=None
        # and NO role checks — it exists purely so the test suite and local
        # load-testing scripts can hit tenant-scoped endpoints without a
        # full JWT. It must never be reachable in production: anyone who
        # can guess or observe a tenant UUID would get unauthenticated
        # access to every endpoint that (incorrectly) omits an explicit
        # CurrentUser/role dependency — which several endpoints across the
        # app do, relying on this middleware layer as their only gate.
        # Disabling it here closes that whole class of bug at the root,
        # on top of fixing the specific endpoints found missing CurrentUser.
        if not settings.is_production:
            tenant_id = request.headers.get("X-Tenant-ID")
            if tenant_id:
                request.state.tenant_id = tenant_id
                request.state.current_user_id = None
                request.state.current_user_roles = []
                return await call_next(request)

        # No context → reject
        return Response(
            content='{"detail":"Authentication required. Provide a Bearer token."}',
            status_code=401,
            media_type="application/json",
            headers={"WWW-Authenticate": "Bearer"},
        )
