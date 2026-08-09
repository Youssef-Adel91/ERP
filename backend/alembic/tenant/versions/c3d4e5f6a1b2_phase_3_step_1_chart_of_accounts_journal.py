"""Phase 3 Step 1: Chart of Accounts & Journal Entries

Revision ID: c3d4e5f6a1b2
Revises: f93809b48226, b2c3d4e5f6a1
Create Date: 2026-07-27 18:00:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a1b2'
down_revision: Union[str, Sequence[str], None] = ('f93809b48226', 'b2c3d4e5f6a1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure 'VOIDED' is allowed in journalentrystatus enum if PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE tenant.journalentrystatus ADD VALUE IF NOT EXISTS 'VOIDED'")

    # 2. Add new columns to tenant.journal_entries
    op.add_column('journal_entries', sa.Column('reference_id', sa.Uuid(), nullable=True), schema='tenant')
    op.add_column(
        'journal_entries',
        sa.Column('entry_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        schema='tenant',
    )
    # Make reference nullable for flexibility
    op.alter_column('journal_entries', 'reference', existing_type=sa.VARCHAR(length=100), nullable=True, schema='tenant')
    op.create_index(op.f('ix_tenant_journal_entries_reference_id'), 'journal_entries', ['reference_id'], unique=False, schema='tenant')

    # 3. Create tenant.journal_entry_lines table
    op.create_table(
        'journal_entry_lines',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('journal_entry_id', sa.Uuid(), nullable=False),
        sa.Column('account_id', sa.Uuid(), nullable=False),
        sa.Column('account_code', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('account_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('debit', sa.Numeric(precision=18, scale=4), server_default=sa.text('0'), nullable=False),
        sa.Column('credit', sa.Numeric(precision=18, scale=4), server_default=sa.text('0'), nullable=False),
        sa.Column('branch_id', sa.Uuid(), nullable=True),
        sa.Column('cost_center_id', sa.Uuid(), nullable=True),
        sa.Column('contact_id', sa.Uuid(), nullable=True),
        sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(length=3), server_default='EGP', nullable=False),
        sa.Column('base_amount', sa.Numeric(precision=18, scale=4), server_default=sa.text('0'), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.CheckConstraint(
            "(debit >= 0 AND credit >= 0) "
            "AND NOT (debit > 0 AND credit > 0) "
            "AND (debit > 0 OR credit > 0)",
            name="ck_journal_entry_lines_debit_xor_credit",
        ),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['tenant.journal_entries.id']),
        sa.ForeignKeyConstraint(['account_id'], ['tenant.accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='tenant',
    )
    op.create_index(op.f('ix_tenant_journal_entry_lines_journal_entry_id'), 'journal_entry_lines', ['journal_entry_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_journal_entry_lines_account_id'), 'journal_entry_lines', ['account_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_journal_entry_lines_account_code'), 'journal_entry_lines', ['account_code'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_journal_entry_lines_branch_id'), 'journal_entry_lines', ['branch_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_journal_entry_lines_cost_center_id'), 'journal_entry_lines', ['cost_center_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_journal_entry_lines_contact_id'), 'journal_entry_lines', ['contact_id'], unique=False, schema='tenant')


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_journal_entry_lines_contact_id'), table_name='journal_entry_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_journal_entry_lines_cost_center_id'), table_name='journal_entry_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_journal_entry_lines_branch_id'), table_name='journal_entry_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_journal_entry_lines_account_code'), table_name='journal_entry_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_journal_entry_lines_account_id'), table_name='journal_entry_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_journal_entry_lines_journal_entry_id'), table_name='journal_entry_lines', schema='tenant')
    op.drop_table('journal_entry_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_journal_entries_reference_id'), table_name='journal_entries', schema='tenant')
    op.alter_column('journal_entries', 'reference', existing_type=sa.VARCHAR(length=100), nullable=False, schema='tenant')
    op.drop_column('journal_entries', 'entry_date', schema='tenant')
    op.drop_column('journal_entries', 'reference_id', schema='tenant')
