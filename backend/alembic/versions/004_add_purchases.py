"""add purchases

Revision ID: 004
Revises: 003
Create Date: 2026-07-25 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'purchase_invoices',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('invoice_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['supplier_id'], ['contacts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_purchase_invoices_status'), 'purchase_invoices', ['status'], unique=False)
    op.create_index(op.f('ix_purchase_invoices_supplier'), 'purchase_invoices', ['supplier_id'], unique=False)
    
    op.create_table(
        'purchase_invoice_lines',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('item_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('line_total', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['purchase_invoices.id'], ),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_purchase_invoice_lines_invoice_id'), 'purchase_invoice_lines', ['invoice_id'], unique=False)
    op.create_index(op.f('ix_purchase_invoice_lines_item_id'), 'purchase_invoice_lines', ['item_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_purchase_invoice_lines_item_id'), table_name='purchase_invoice_lines')
    op.drop_index(op.f('ix_purchase_invoice_lines_invoice_id'), table_name='purchase_invoice_lines')
    op.drop_table('purchase_invoice_lines')
    
    op.drop_index(op.f('ix_purchase_invoices_supplier'), table_name='purchase_invoices')
    op.drop_index(op.f('ix_purchase_invoices_status'), table_name='purchase_invoices')
    op.drop_table('purchase_invoices')
