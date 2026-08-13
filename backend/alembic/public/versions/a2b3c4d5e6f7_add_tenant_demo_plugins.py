"""add_tenant_demo_plugins

Revision ID: a2b3c4d5e6f7
Revises: 3c9e6a1f7d22
Create Date: 2026-08-10 00:00:00.000000+00:00

Adds `demo_plugins` (JSON list) to public.tenants — tracks which plugins a
tenant is trying in free-demo mode (picked during onboarding), separate
from `active_plugins` (paid/fully installed). Defensive: skips if the
column already exists.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "3c9e6a1f7d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'demo_plugins'"
        )
    ).scalar()
    if not exists:
        op.add_column(
            "tenants",
            sa.Column("demo_plugins", sa.JSON(), server_default="[]", nullable=False),
            schema="public",
        )


def downgrade() -> None:
    op.drop_column("tenants", "demo_plugins", schema="public")
