"""fix_whatsapp_config_timestamps

The 3c9e6a1f7d22 migration that created public.whatsapp_tenant_configs
declared created_at/updated_at as `nullable=False` with NO server_default
— unlike every other public-schema table's migration (see e.g.
49d0941c6745's own created_at/updated_at columns, and the tenants/users
tables from dab1b0c153e8), which all set
`server_default=sa.text('now()')`.

The ORM model (app.core.db.base.BaseMixin) DOES declare
`sa_column_kwargs={"server_default": func.now(), ...}` for both columns —
but that's Python-side model metadata, not DDL. Since this table's actual
column definitions came from op.create_table() in 3c9e6a1f7d22 rather
than from Base.metadata.create_all(), the live Postgres column never
actually got that default. SQLAlchemy therefore omits created_at/
updated_at from every INSERT it emits for this model (correctly trusting
the declared server_default to supply them) — and every such INSERT was
failing with:

  NotNullViolationError: null value in column "created_at" of relation
  "whatsapp_tenant_configs" violates not-null constraint

...which app.plugins.whatsapp.api.config.py's blanket
`except IntegrityError` handler silently mapped to a generic (and
misleading) 409 "phone number already registered to another tenant"
response — discovered via live end-to-end verification (11 Sep 2026):
every PUT /api/v1/whatsapp/config call failed this way, even with a
guaranteed-unique phone_number_id, for every tenant, always.

This migration brings the live column defaults in line with what the ORM
model has always declared, closing the drift.

Revision ID: f1a2b3c4d5e6
Revises: b3c4d5e6f7a8
Create Date: 2026-09-11 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'b3c4d5e6f7a8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        'whatsapp_tenant_configs', 'created_at',
        server_default=sa.text('now()'),
        schema='public',
    )
    op.alter_column(
        'whatsapp_tenant_configs', 'updated_at',
        server_default=sa.text('now()'),
        schema='public',
    )
    # Backfill any pre-existing rows that predate this fix (defensive —
    # none are expected in practice since every prior INSERT attempt
    # failed and rolled back, but this makes the migration safe to run
    # against any state).
    op.execute(
        "UPDATE public.whatsapp_tenant_configs "
        "SET created_at = now() WHERE created_at IS NULL"
    )
    op.execute(
        "UPDATE public.whatsapp_tenant_configs "
        "SET updated_at = now() WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    op.alter_column(
        'whatsapp_tenant_configs', 'updated_at',
        server_default=None,
        schema='public',
    )
    op.alter_column(
        'whatsapp_tenant_configs', 'created_at',
        server_default=None,
        schema='public',
    )
