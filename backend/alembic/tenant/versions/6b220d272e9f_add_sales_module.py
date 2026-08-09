"""add_sales_module

Revision ID: 6b220d272e9f
Revises: f93809b48226
Create Date: 2026-07-27 00:02:08.010956+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '6b220d272e9f'
down_revision: Union[str, None] = 'f93809b48226'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TYPE IF EXISTS tenant.salesorderstatus CASCADE")
    op.create_table('sales_orders',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_number', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('contact_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'CONFIRMED', 'PARTIALLY_FULFILLED', 'FULFILLED', 'INVOICED', 'CANCELLED', name='salesorderstatus', schema='tenant'), nullable=False),
    sa.Column('order_date', sa.Date(), nullable=False),
    sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(length=3), nullable=False),
    sa.Column('total_amount', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index(op.f('ix_tenant_sales_orders_contact_id'), 'sales_orders', ['contact_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_orders_order_number'), 'sales_orders', ['order_number'], unique=True, schema='tenant')
    op.create_table('sales_order_lines',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('order_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('variant_id', sa.Uuid(), nullable=True),
    sa.Column('uom_id', sa.Uuid(), nullable=True),
    sa.Column('qty', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('fulfilled_qty', sa.Numeric(precision=18, scale=4), server_default=sa.text('0'), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.Column('line_total', sa.Numeric(precision=18, scale=4), nullable=False),
    sa.CheckConstraint('qty > 0', name='ck_sales_order_lines_qty_positive'),
    sa.CheckConstraint('unit_price >= 0', name='ck_sales_order_lines_unit_price_non_negative'),
    sa.CheckConstraint('fulfilled_qty >= 0', name='ck_sales_order_lines_fulfilled_qty_non_negative'),
    sa.ForeignKeyConstraint(['order_id'], ['tenant.sales_orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='tenant'
    )
    op.create_index(op.f('ix_tenant_sales_order_lines_item_id'), 'sales_order_lines', ['item_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_order_lines_order_id'), 'sales_order_lines', ['order_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_order_lines_uom_id'), 'sales_order_lines', ['uom_id'], unique=False, schema='tenant')
    op.create_index(op.f('ix_tenant_sales_order_lines_variant_id'), 'sales_order_lines', ['variant_id'], unique=False, schema='tenant')


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_sales_order_lines_variant_id'), table_name='sales_order_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_order_lines_uom_id'), table_name='sales_order_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_order_lines_order_id'), table_name='sales_order_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_order_lines_item_id'), table_name='sales_order_lines', schema='tenant')
    op.drop_table('sales_order_lines', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_orders_order_number'), table_name='sales_orders', schema='tenant')
    op.drop_index(op.f('ix_tenant_sales_orders_contact_id'), table_name='sales_orders', schema='tenant')
    op.drop_table('sales_orders', schema='tenant')
    op.execute("DROP TYPE IF EXISTS tenant.salesorderstatus CASCADE")
