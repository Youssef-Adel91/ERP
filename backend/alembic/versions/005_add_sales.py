"""add sales

Revision ID: 005_add_sales
Revises: 004_add_purchases
Create Date: 2026-07-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '005_add_sales'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. We must run this creation for ALL existing tenant schemas.
    # We fetch them from public.tenants
    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM public.tenants")).fetchall()

    for (tenant_id,) in tenants:
        schema_name = f"tenant_{str(tenant_id).replace('-', '_')}"
        
        # Set search path to this tenant
        conn.execute(sa.text(f'SET search_path TO "{schema_name}"'))
        
        # Create sales_invoices
        op.create_table('sales_invoices',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('customer_id', sa.UUID(), nullable=False),
            sa.Column('invoice_date', sa.DateTime(), nullable=False),
            sa.Column('total_amount', sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('created_by', sa.UUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['customer_id'], ['contacts.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_sales_invoices_customer', 'sales_invoices', ['customer_id'], unique=False)
        op.create_index('ix_sales_invoices_status', 'sales_invoices', ['status'], unique=False)

        # Create sales_invoice_lines
        op.create_table('sales_invoice_lines',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('invoice_id', sa.UUID(), nullable=False),
            sa.Column('item_id', sa.UUID(), nullable=False),
            sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column('line_total', sa.Numeric(precision=18, scale=4), nullable=False),
            sa.ForeignKeyConstraint(['invoice_id'], ['sales_invoices.id'], ),
            sa.ForeignKeyConstraint(['item_id'], ['items.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_sales_invoice_lines_invoice_id', 'sales_invoice_lines', ['invoice_id'], unique=False)
        op.create_index('ix_sales_invoice_lines_item_id', 'sales_invoice_lines', ['item_id'], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM public.tenants")).fetchall()

    for (tenant_id,) in tenants:
        schema_name = f"tenant_{str(tenant_id).replace('-', '_')}"
        conn.execute(sa.text(f'SET search_path TO "{schema_name}"'))
        
        op.drop_index('ix_sales_invoice_lines_item_id', table_name='sales_invoice_lines')
        op.drop_index('ix_sales_invoice_lines_invoice_id', table_name='sales_invoice_lines')
        op.drop_table('sales_invoice_lines')
        
        op.drop_index('ix_sales_invoices_status', table_name='sales_invoices')
        op.drop_index('ix_sales_invoices_customer', table_name='sales_invoices')
        op.drop_table('sales_invoices')
