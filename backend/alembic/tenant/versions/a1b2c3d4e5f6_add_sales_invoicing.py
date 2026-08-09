"""add_sales_invoicing

Revision ID: a1b2c3d4e5f6
Revises: 6b220d272e9f
Create Date: 2026-07-27 00:30:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6b220d272e9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TYPE IF EXISTS tenant.salesinvoicestatus CASCADE")
    op.create_table(
        'sales_invoices',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invoice_number', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.Enum('DRAFT', 'POSTED', 'PAID', 'CANCELLED', name='salesinvoicestatus', schema='tenant'), server_default='DRAFT', nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('tax_total', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('grand_total', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['tenant.sales_orders.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='tenant'
    )
    op.create_index(op.f('ix_tenant_sales_invoices_contact_id'), 'sales_invoices', ['contact_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_invoices_invoice_number'), 'sales_invoices', ['invoice_number'], unique=True, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_invoices_order_id'), 'sales_invoices', ['order_id'], unique=False, schema='tenant')

    op.create_table(
        'sales_invoice_lines',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('invoice_id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('variant_id', sa.Uuid(), nullable=True),
        sa.Column('uom_id', sa.Uuid(), nullable=True),
        sa.Column('qty', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('line_total', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('tax_rate', sa.Numeric(precision=18, scale=4), server_default=sa.text('0.1400'), nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=18, scale=4), server_default=sa.text('0.0000'), nullable=False),
        sa.CheckConstraint('qty > 0', name='ck_sales_invoice_lines_qty_positive'),
        sa.CheckConstraint('unit_price >= 0', name='ck_sales_invoice_lines_unit_price_non_negative'),
        sa.CheckConstraint('tax_rate >= 0', name='ck_sales_invoice_lines_tax_rate_non_negative'),
        sa.CheckConstraint('tax_amount >= 0', name='ck_sales_invoice_lines_tax_amount_non_negative'),
        sa.ForeignKeyConstraint(['invoice_id'], ['tenant.sales_invoices.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='tenant'
    )
    op.create_index(op.f('ix_tenant_sales_invoice_lines_invoice_id'), 'sales_invoice_lines', ['invoice_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_invoice_lines_item_id'), 'sales_invoice_lines', ['item_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_invoice_lines_uom_id'), 'sales_invoice_lines', ['uom_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_invoice_lines_variant_id'), 'sales_invoice_lines', ['variant_id'], unique=False, schema='tenant')


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_sales_invoice_lines_variant_id'), table_name='sales_invoice_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_invoice_lines_uom_id'), table_name='sales_invoice_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_invoice_lines_item_id'), table_name='sales_invoice_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_invoice_lines_invoice_id'), table_name='sales_invoice_lines', schema='tenant')
    op.drop_table('sales_invoice_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_invoices_order_id'), table_name='sales_invoices', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_invoices_invoice_number'), table_name='sales_invoices', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_invoices_contact_id'), table_name='sales_invoices', schema='tenant')
    op.drop_table('sales_invoices', schema='tenant')
    op.execute("DROP TYPE IF EXISTS tenant.salesinvoicestatus CASCADE")
