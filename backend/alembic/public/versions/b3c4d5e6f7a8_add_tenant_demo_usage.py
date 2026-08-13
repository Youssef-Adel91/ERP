"""add_tenant_demo_usage

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-10 02:00:00.000000+00:00

Adds `demo_usage` (JSON object, plugin_key -> mutating-request count) to
public.tenants — backs the fixed-operation-count demo limit enforced in
app/core/dependencies/plugin_gate.py (require_plugin). Defensive: skips if
the column already exists, following the same pattern as
a2b3c4d5e6f7_add_tenant_demo_plugins.py.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'demo_usage'"
        )
    ).scalar()
    if not exists:
        op.add_column(
            "tenants",
            sa.Column("demo_usage", sa.JSON(), server_default="{}", nullable=False),
            schema="public",
        )


def downgrade() -> None:
    op.drop_column("tenants", "demo_usage", schema="public")
