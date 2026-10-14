"""merge_tenant_heads

Revision ID: b7389da6f618
Revises: A1b2c3d4e5f6, d8e9f0a1b2c3
Create Date: 2026-09-09 20:18:10.122975+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b7389da6f618'
down_revision: Union[str, None] = ('A1b2c3d4e5f6', 'd8e9f0a1b2c3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
