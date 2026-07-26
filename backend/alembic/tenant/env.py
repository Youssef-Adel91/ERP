"""
alembic/tenant/env.py — Alembic Environment for Tenant Schemas

This script handles migrations for a specific tenant schema, passed via -x schema=<name>.
"""
from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import app.core.audit.models
import app.core.observability.models
import app.core.sequences.models
import app.modules.accounting.models
import app.modules.contacts.models

# Import models to ensure they are registered with TenantBase.metadata
import app.modules.core.models
import app.plugins.inventory.models  # noqa: F401
from app.core.config import settings
from app.core.db.base import TenantBase

target_metadata = TenantBase.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def do_run_migrations(connection, schema_name: str) -> None:
    """Execute Alembic migrations for a single tenant schema."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema=schema_name,
        include_schemas=False,  # DO NOT include public or other schemas
        compare_type=True,
        compare_server_default=True,
        # Only include tables inside this exact schema and ignore alembic_version
        include_object=lambda obj, name, type_, reflected, compare_to: (
            False if name == "alembic_version" else (
                obj.schema == "tenant" if type_ == "table" else True
            )
        ),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Read target schema from `-x schema=tenant_xxx`
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")
    
    if not schema_name:
        raise ValueError("Tenant migrations require a schema argument: -x schema=<name>")

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # We enforce schema translation at the connection level for the tenant schema.
        conn_tenant = await connection.execution_options(
            schema_translate_map={"tenant": schema_name, "public": "public"},
        )
        await conn_tenant.run_sync(do_run_migrations, schema_name)

    await connectable.dispose()


def run_migrations_offline() -> None:
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")
    
    if not schema_name:
        raise ValueError("Tenant migrations require a schema argument: -x schema=<name>")

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema_name,
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
