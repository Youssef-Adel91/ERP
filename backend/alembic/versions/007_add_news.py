"""add news

Revision ID: 007_add_news
Revises: 006_add_rbac
Create Date: 2026-07-25 20:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '007_add_news'
down_revision: Union[str, None] = '006_add_rbac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We need to run this on all existing tenant schemas.
    # 1. Find all tenant schemas
    conn = op.get_bind()
    schemas = conn.execute(text("SELECT schema_name FROM public.tenants")).fetchall()
    
    for (schema_name,) in schemas:
        op.execute(f'SET search_path TO "{schema_name}", public')
        
        op.create_table(
            'announcements',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('created_by', sa.UUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            schema=schema_name
        )


def downgrade() -> None:
    conn = op.get_bind()
    schemas = conn.execute(text("SELECT schema_name FROM public.tenants")).fetchall()
    
    for (schema_name,) in schemas:
        op.execute(f'SET search_path TO "{schema_name}", public')
        op.drop_table('announcements', schema=schema_name)
