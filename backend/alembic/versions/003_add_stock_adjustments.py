"""add stock adjustments

Revision ID: 003
Revises: 002
Create Date: 2026-07-25 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Because this is a multi-tenant DB, the standard way in this app 
    # to provision tables might just be create_all() on new tenants. 
    # But for existing tenants, we need to create the table in each schema.
    # We will just write the DDL as if it's running on the current search_path,
    # or the user can run it in a loop across schemas if needed.
    
    op.create_table(
        'stock_adjustments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('notes', sa.String(length=2000), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table(
        'stock_adjustment_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('adjustment_id', sa.UUID(), nullable=False),
        sa.Column('item_id', sa.UUID(), nullable=False),
        sa.Column('quantity_change', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.ForeignKeyConstraint(['adjustment_id'], ['stock_adjustments.id'], ),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_adjustment_items_adjustment_id'), 'stock_adjustment_items', ['adjustment_id'], unique=False)
    op.create_index(op.f('ix_stock_adjustment_items_item_id'), 'stock_adjustment_items', ['item_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_stock_adjustment_items_item_id'), table_name='stock_adjustment_items')
    op.drop_index(op.f('ix_stock_adjustment_items_adjustment_id'), table_name='stock_adjustment_items')
    op.drop_table('stock_adjustment_items')
    op.drop_table('stock_adjustments')
