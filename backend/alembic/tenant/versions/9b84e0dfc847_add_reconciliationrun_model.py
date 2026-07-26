"""Add ReconciliationRun model

Revision ID: 9b84e0dfc847
Revises: f3a8c91d4e72
Create Date: 2026-07-26 16:45:01.136721+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9b84e0dfc847'
down_revision: str | None = 'f3a8c91d4e72'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema() -> str:
    from alembic import context as alembic_context
    schema = alembic_context.get_context().version_table_schema
    if not schema:
        raise RuntimeError("Schema not found in Alembic context.")
    return schema


def upgrade() -> None:
    schema_name = _get_schema()
    
    op.execute(f"DROP TYPE IF EXISTS {schema_name}.reconciliationstatus CASCADE")
    
    op.create_table('reconciliation_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('PASS', 'FAIL', 'ERROR', name='reconciliationstatus', schema=schema_name, create_type=False), nullable=False),
    sa.Column('failed_checks', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema=schema_name,
    )


def downgrade() -> None:
    schema_name = _get_schema()
    op.drop_table('reconciliation_runs', schema=schema_name)
    op.execute(f"DROP TYPE {schema_name}.reconciliationstatus")
