"""add rbac

Revision ID: 006_add_rbac
Revises: 005_add_sales
Create Date: 2026-07-25 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '006_add_rbac'
down_revision: Union[str, None] = '005_add_sales'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We are modifying the public.users table.
    # Add `role` column
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=20), server_default='OWNER', nullable=False),
        schema='public'
    )
    
    # Drop `roles` column
    op.drop_column('users', 'roles', schema='public')


def downgrade() -> None:
    # Add back `roles` column
    op.add_column(
        'users',
        sa.Column('roles', postgresql.JSON(astext_type=sa.Text()), server_default='["OWNER"]', nullable=False),
        schema='public'
    )
    
    # Drop `role` column
    op.drop_column('users', 'role', schema='public')
