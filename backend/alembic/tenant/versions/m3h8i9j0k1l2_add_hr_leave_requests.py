"""Add HR leave requests + employee leave balance

Revision ID: m3h8i9j0k1l2
Revises: a4c3d2e1f0b9
Create Date: 2026-08-19 00:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'm3h8i9j0k1l2'
down_revision: str | None = 'a4c3d2e1f0b9'
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

    op.add_column(
        'hr_employees',
        sa.Column('leave_balance_days', sa.Integer(), server_default='21', nullable=False),
        schema=schema_name,
    )

    op.create_table(
        'hr_leave_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('employee_id', sa.Uuid(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='leaverequeststatus', schema=schema_name), nullable=False),
        sa.Column('decided_by', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], [f'{schema_name}.hr_employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema_name,
    )
    op.create_index(
        op.f('ix_tenant_hr_leave_requests_employee_id'),
        'hr_leave_requests', ['employee_id'], unique=False, schema=schema_name,
    )


def downgrade() -> None:
    schema_name = _get_schema()
    op.drop_index(op.f('ix_tenant_hr_leave_requests_employee_id'), table_name='hr_leave_requests', schema=schema_name)
    op.drop_table('hr_leave_requests', schema=schema_name)
    op.execute(f"DROP TYPE {schema_name}.leaverequeststatus")
    op.drop_column('hr_employees', 'leave_balance_days', schema=schema_name)
