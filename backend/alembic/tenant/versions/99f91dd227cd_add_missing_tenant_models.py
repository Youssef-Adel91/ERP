"""add_missing_tenant_models

Revision ID: 99f91dd227cd
Revises: l2g7h8i9j0k1
Create Date: 2026-08-11 00:06:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '99f91dd227cd'
down_revision = 'l2g7h8i9j0k1'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('case_types',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('name_ar', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('plugin_key', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('initial_stage', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('stages', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('meta', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_case_types_code'),
    schema='tenant'
    )
    op.create_index(op.f('ix_tenant_case_types_code'), 'case_types', ['code'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_case_types_plugin_key'), 'case_types', ['plugin_key'], unique=False, schema='tenant')
    op.create_table('case_vendors',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('name_ar', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('vendor_type', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
    sa.Column('contact_person', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index('ix_case_vendors_type', 'case_vendors', ['vendor_type'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_case_vendors_name'), 'case_vendors', ['name'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_case_vendors_vendor_type'), 'case_vendors', ['vendor_type'], unique=False, schema='tenant')
    op.create_table('case_resources',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resource_type', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('attributes', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index('ix_case_resources_type_status', 'case_resources', ['resource_type', 'status'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_case_resources_code'), 'case_resources', ['code'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_case_resources_resource_type'), 'case_resources', ['resource_type'], unique=False, schema='tenant')
    op.create_table('cases',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('case_type_id', sa.Uuid(), nullable=False),
    sa.Column('current_stage', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('resource_id', sa.Uuid(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('data', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.ForeignKeyConstraint(['case_type_id'], ['tenant.case_types.id'], ),
    sa.ForeignKeyConstraint(['resource_id'], ['tenant.case_resources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index('ix_cases_resource_dates', 'cases', ['resource_id', 'start_date', 'end_date'], unique=False, schema='tenant')
    op.create_index('ix_cases_status', 'cases', ['status'], unique=False, schema='tenant')
    op.create_index('ix_cases_type_stage', 'cases', ['case_type_id', 'current_stage'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_cases_case_type_id'), 'cases', ['case_type_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_cases_current_stage'), 'cases', ['current_stage'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_cases_resource_id'), 'cases', ['resource_id'], unique=False, schema='tenant')
    op.create_table('hr_employees',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('last_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('national_id', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('base_salary', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('hire_date', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'ON_LEAVE', 'TERMINATED', name='employeestatus'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index(op.f('ix_tenant_hr_employees_national_id'), 'hr_employees', ['national_id'], unique=True, schema='tenant')
    op.create_table('pos_cash_shifts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('opened_by', sa.Uuid(), nullable=False),
    sa.Column('closed_by', sa.Uuid(), nullable=True),
    sa.Column('status', postgresql.ENUM('OPEN', 'CLOSED', name='shiftstatus', create_type=False), nullable=False),
    sa.Column('opening_balance', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('closing_balance', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('expected_balance', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('variance', sa.Numeric(precision=18, scale=4), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index(op.f('ix_tenant_pos_cash_shifts_opened_by'), 'pos_cash_shifts', ['opened_by'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_pos_cash_shifts_status'), 'pos_cash_shifts', ['status'], unique=False, schema='tenant')

def downgrade() -> None:
    pass
