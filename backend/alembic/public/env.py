"""
alembic/public/env.py — Alembic Environment for Public Schema

This script handles migrations for the global `public` schema ONLY.
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

# Import models to ensure they are registered with PublicBase.metadata
from app.core.config import settings
from app.core.db.base import PublicBase

target_metadata = PublicBase.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def do_run_migrations(connection) -> None:
    """Execute Alembic migrations for the public schema."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema="public",
        include_schemas=False,  # DO NOT include tenant schemas
        compare_type=True,
        compare_server_default=True,
        # Ensure we only include tables inside the public schema and ignore alembic_version
        include_object=lambda obj, name, type_, reflected, compare_to: (
            False if name == "alembic_version" else (
                obj.schema == "public" or obj.schema is None if type_ == "table" else True
            )
        ),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # We enforce schema translation at the connection level for public.
        # This aligns with how tenant_session vs public_session works.
        conn_public = await connection.execution_options(
            schema_translate_map={"public": "public", "tenant": None},
        )
        await conn_public.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
