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
  2. SET search_path TO tenant_{id}
  3. SQLModel.metadata.create_all(conn, tables=[...tenant tables...])
     → Creates accounting, contact, inventory tables in the new schema
  4. Seeds default Chart of Accounts (system accounts required for events)
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


async def provision_tenant_schema(tenant_id: str) -> str:
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
    from app.plugins.inventory.models import Invoice, InvoiceLine, Item

    schema = schema_for(tenant_id)

    # Tables that belong inside the tenant schema.
    # ORDER IS CRITICAL — referenced tables must precede tables with FKs:
    #   Contact  must come before Invoice   (Invoice.contact_id → contacts.id)
    #   Item     must come before InvoiceLine (InvoiceLine.item_id → items.id)
    #   Invoice  must come before InvoiceLine (InvoiceLine.invoice_id → invoices.id)
    tenant_tables = [
        Account.__table__,
        JournalEntry.__table__,
        TransactionLine.__table__,
        Contact.__table__,
        Item.__table__,
        Invoice.__table__,
        InvoiceLine.__table__,
    ]

    # ── Step 1 & 2: Create schema + tables ────────────────────────────────────
    async with engine.begin() as conn:
        # CREATE SCHEMA (idempotent)
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

        # Set execution options for schema translation for DDL
        conn_translated = await conn.execution_options(schema_translate_map={"tenant": schema})

        # Create all tenant tables using SQLModel metadata
        # `tables=` limits create_all to ONLY these tables — public schema
        # tables (Tenant, User) are excluded and left untouched.
        def _create(sync_conn):
            SQLModel.metadata.create_all(sync_conn, tables=tenant_tables)

        await conn_translated.run_sync(_create)

    # ── Step 3: Seed default Chart of Accounts ────────────────────────────────
    # Each new tenant gets the same baseline chart, ready for event handlers.
    async with tenant_session(tenant_id) as session:
        for acct_data in DEFAULT_ACCOUNTS:
            account = Account(
                code=acct_data["code"],
                name=acct_data["name"],
                name_ar=acct_data.get("name_ar"),
                account_type=acct_data["account_type"],
                is_system=acct_data.get("is_system", False),
            )
            session.add(account)

    logger.info(
        "✅ Tenant schema '%s' provisioned with %d default accounts.",
        schema,
        len(DEFAULT_ACCOUNTS),
    )
    return schema


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
_BYPASS_PATHS = {"/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico", "/metrics"}
_BYPASS_PREFIXES = (
    "/api/v1/system/auth/",
    "/api/v1/system/tenants/register",
    "/api/v1/auth/",            # The /api/v1/auth/register shortcut
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

        # Strategy 2 — X-Tenant-ID header (internal / testing)
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
