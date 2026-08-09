"""Phase 5 Step 3: Item Coding Registry (EgsCode)

Revision ID: j0e5f6g7h8i9
Revises: i9d4e5f6g7h8
Create Date: 2026-07-31 03:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j0e5f6g7h8i9"
down_revision: Union[str, None] = "i9d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "egs_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("code_type", sa.String(length=10), nullable=False, server_default="EGS"),
        sa.Column("code_value", sa.String(length=100), nullable=False),
        sa.Column("parent_code", sa.String(length=100), nullable=True),
        sa.Column("name_ar", sa.String(length=255), nullable=True),
        sa.Column("name_en", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="Approved"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_egs_codes")),
        sa.UniqueConstraint("item_id", "variant_id", "code_type", name="uq_egs_codes_item_variant_type"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_egs_codes_tenant_id"),
        "egs_codes",
        ["tenant_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_egs_codes_item_id"),
        "egs_codes",
        ["item_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_egs_codes_variant_id"),
        "egs_codes",
        ["variant_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_egs_codes_code_type"),
        "egs_codes",
        ["code_type"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_egs_codes_code_value"),
        "egs_codes",
        ["code_value"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_egs_codes_is_active"),
        "egs_codes",
        ["is_active"],
        unique=False,
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_egs_codes_is_active"), table_name="egs_codes", schema="tenant")
    op.drop_index(op.f("ix_tenant_egs_codes_code_value"), table_name="egs_codes", schema="tenant")
    op.drop_index(op.f("ix_tenant_egs_codes_code_type"), table_name="egs_codes", schema="tenant")
    op.drop_index(op.f("ix_tenant_egs_codes_variant_id"), table_name="egs_codes", schema="tenant")
    op.drop_index(op.f("ix_tenant_egs_codes_item_id"), table_name="egs_codes", schema="tenant")
    op.drop_index(op.f("ix_tenant_egs_codes_tenant_id"), table_name="egs_codes", schema="tenant")
    op.drop_table("egs_codes", schema="tenant")
