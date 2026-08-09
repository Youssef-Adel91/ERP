"""add_sales_returns

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-07-27 01:00:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TYPE IF EXISTS tenant.salesreturnstatus CASCADE")
    op.create_table(
        'sales_returns',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('return_number', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=True),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('credit_note_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'RECEIVED', 'CREDITED', name='salesreturnstatus', schema='tenant'), server_default='DRAFT', nullable=False),
        sa.Column('return_date', sa.Date(), nullable=False),
        sa.Column('subtotal', sa.Numeric(18, 4), nullable=False),
        sa.Column('tax_total', sa.Numeric(18, 4), nullable=False),
        sa.Column('grand_total', sa.Numeric(18, 4), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['tenant.sales_invoices.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['tenant.sales_orders.id'], ),
        sa.ForeignKeyConstraint(['credit_note_id'], ['tenant.sales_invoices.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='tenant'
    )
    op.create_index(op.f('ix_tenant_sales_returns_contact_id'), 'sales_returns', ['contact_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_returns_id'), 'sales_returns', ['id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_returns_invoice_id'), 'sales_returns', ['invoice_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_returns_order_id'), 'sales_returns', ['order_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_returns_credit_note_id'), 'sales_returns', ['credit_note_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_returns_return_number'), 'sales_returns', ['return_number'], unique=True, schema='tenant')

    op.create_table(
        'sales_return_lines',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('return_id', sa.Uuid(), nullable=False),
        sa.Column('original_invoice_line_id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('variant_id', sa.Uuid(), nullable=True),
        sa.Column('uom_id', sa.Uuid(), nullable=True),
        sa.Column('batch_id', sa.Uuid(), nullable=True),
        sa.Column('serial_id', sa.Uuid(), nullable=True),
        sa.Column('qty', sa.Numeric(18, 4), nullable=False),
        sa.Column('unit_price', sa.Numeric(18, 4), nullable=False),
        sa.Column('line_total', sa.Numeric(18, 4), nullable=False),
        sa.Column('tax_rate', sa.Numeric(18, 4), server_default=sa.text('0.1400'), nullable=False),
        sa.Column('tax_amount', sa.Numeric(18, 4), server_default=sa.text('0.0000'), nullable=False),
        sa.CheckConstraint('qty > 0', name='ck_sales_return_lines_qty_positive'),
        sa.CheckConstraint('unit_price >= 0', name='ck_sales_return_lines_unit_price_non_negative'),
        sa.CheckConstraint('tax_rate >= 0', name='ck_sales_return_lines_tax_rate_non_negative'),
        sa.CheckConstraint('tax_amount >= 0', name='ck_sales_return_lines_tax_amount_non_negative'),
        sa.ForeignKeyConstraint(['original_invoice_line_id'], ['tenant.sales_invoice_lines.id'], ),
        sa.ForeignKeyConstraint(['return_id'], ['tenant.sales_returns.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='tenant'
    )
    op.create_index(op.f('ix_tenant_sales_return_lines_batch_id'), 'sales_return_lines', ['batch_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_id'), 'sales_return_lines', ['id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_item_id'), 'sales_return_lines', ['item_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_original_invoice_line_id'), 'sales_return_lines', ['original_invoice_line_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_return_id'), 'sales_return_lines', ['return_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_serial_id'), 'sales_return_lines', ['serial_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_uom_id'), 'sales_return_lines', ['uom_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_return_lines_variant_id'), 'sales_return_lines', ['variant_id'], unique=False, schema='tenant')


def downgrade() -> None:
    op.drop_table('sales_return_lines', schema='tenant')
    op.drop_table('sales_returns', schema='tenant')
    op.execute("DROP TYPE IF EXISTS tenant.salesreturnstatus CASCADE")
