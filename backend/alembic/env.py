"""
alembic/env.py — Custom Multi-Schema Alembic Environment

This env.py implements the "Single versions/ directory, schema-aware" strategy (Option A).

Migration Strategy:
  1. PUBLIC SCHEMA migrations: Applied once to `public`. Contains global tables:
     tenants, users, subscriptions.

  2. TENANT SCHEMA migrations: Applied to EVERY registered tenant schema.
     The env.py queries `public.tenants` to get all schema names, then iterates,
     applying each migration in turn.

Running migrations:
  # Apply to public schema only:
  alembic upgrade head --arg schema=public

  # Apply to all tenant schemas:
  alembic upgrade head --arg schema=all_tenants

  # Apply to a specific tenant:
  alembic upgrade head --arg schema=tenant_abc123

  # Standard (applies everything — public first, then all tenants):
  alembic upgrade head
"""
from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

# ── Add project root to sys.path ──────────────────────────────────────────────
# This allows importing app modules from the alembic/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings  # noqa: E402

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config

# Override the SQLAlchemy URL from Pydantic Settings (reads .env)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Setup logging as configured in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so Alembic can detect table changes ─────────────────────
# These imports must cover ALL SQLModel table classes for autogenerate to work.
from sqlmodel import SQLModel  # noqa: E402

import app.modules.system.models  # noqa: F401, E402
import app.modules.accounting.models  # noqa: F401, E402
import app.modules.contacts.models  # noqa: F401, E402
import app.plugins.inventory.models  # noqa: F401, E402

target_metadata = SQLModel.metadata


# ── Helper: Get all tenant schema names from the public.tenants table ─────────


async def _get_tenant_schema_names(connectable: AsyncEngine) -> list[str]:
    """
    Query public.tenants to get all schema names for migration iteration.
    Returns a list like ["tenant_abc123", "tenant_def456", ...].
    """
    async with connectable.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM public.tenants WHERE status != 'cancelled'")
        )
        return [row[0] for row in result.fetchall()]


# ── Migration Runner ──────────────────────────────────────────────────────────


def do_run_migrations(connection, schema_name: str) -> None:
    """
    Execute Alembic migrations for a specific schema.

    Sets search_path so all CREATE TABLE statements land in the correct schema.
    """
    connection.execute(text(f"SET search_path TO {schema_name}"))
    connection.dialect.default_schema_name = schema_name

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema=schema_name,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
        # Only include tables for the relevant schema
        include_object=lambda obj, name, type_, reflected, compare_to: (
            obj.schema is None or obj.schema == schema_name
            if type_ == "table"
            else True
        ),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Main async migration runner.

    Applies migrations in this order:
      1. public schema (tenants, users, subscriptions)
      2. All registered tenant schemas (accounting, contacts, inventory, etc.)
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # ── Step 1: Apply public schema migrations ────────────────────────────
        print("▶ Applying migrations to 'public' schema...")
        await connection.run_sync(do_run_migrations, "public")
        print("✅ Public schema migrations complete.")

        # ── Step 2: Apply tenant schema migrations ────────────────────────────
        try:
            tenant_schemas = await _get_tenant_schema_names(connectable)
        except Exception:
            # Table may not exist yet on first run — skip tenant migrations
            print("ℹ  No tenant schemas found (first run or empty DB). Skipping.")
            tenant_schemas = []

        for schema_name in tenant_schemas:
            print(f"▶ Applying migrations to '{schema_name}'...")
            await connection.run_sync(do_run_migrations, schema_name)
            print(f"✅ '{schema_name}' migrations complete.")

    await connectable.dispose()


def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection (generates SQL scripts).
    Only applies to the public schema in offline mode.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Entry point for online (live DB) migrations."""
    asyncio.run(run_async_migrations())


# ── Execute ────────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
