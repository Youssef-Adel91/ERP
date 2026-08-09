"""Phase 4b Step 3: Landed Cost Allocation tables

Revision ID: g7b2c3d4e5f6
Revises: f6a1b2c3d4e5
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g7b2c3d4e5f6"
down_revision: Union[str, None] = "f6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. import_shipments
    op.create_table(
        "import_shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("po_id", sa.Uuid(), nullable=True),
        sa.Column("shipment_ref", sa.String(length=50), nullable=False),
        sa.Column("supplier_ids", sa.JSON(), nullable=False),
        sa.Column("po_ids", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="EGP", nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), server_default="1.000000", nullable=False),
        sa.Column("total_landed_cost", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_import_shipments_shipment_ref"),
        "import_shipments",
        ["shipment_ref"],
        unique=True,
        schema="tenant",
    )

    # 2. landed_cost_lines
    op.create_table(
        "landed_cost_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("cost_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="EGP", nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), server_default="1.000000", nullable=False),
        sa.Column("allocation_basis", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["tenant.import_shipments.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_landed_cost_lines_shipment_id"),
        "landed_cost_lines",
        ["shipment_id"],
        unique=False,
        schema="tenant",
    )

    # 3. landed_cost_allocations
    op.create_table(
        "landed_cost_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("landed_cost_line_id", sa.Uuid(), nullable=False),
        sa.Column("target_grn_line_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["landed_cost_line_id"], ["tenant.landed_cost_lines.id"]),
        sa.ForeignKeyConstraint(["target_grn_line_id"], ["tenant.goods_receipt_lines.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_landed_cost_allocations_landed_cost_line_id"),
        "landed_cost_allocations",
        ["landed_cost_line_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_landed_cost_allocations_target_grn_line_id"),
        "landed_cost_allocations",
        ["target_grn_line_id"],
        unique=False,
        schema="tenant",
    )
    op.add_column(
        "goods_receipt_lines",
        sa.Column(
            "expected_landed_unit_cost",
            sa.Numeric(precision=18, scale=4),
            nullable=True,
        ),
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_column("goods_receipt_lines", "expected_landed_unit_cost", schema="tenant")
    op.drop_index(
        op.f("ix_tenant_landed_cost_allocations_target_grn_line_id"),
        table_name="landed_cost_allocations",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_landed_cost_allocations_landed_cost_line_id"),
        table_name="landed_cost_allocations",
        schema="tenant",
    )
    op.drop_table("landed_cost_allocations", schema="tenant")

    op.drop_index(
        op.f("ix_tenant_landed_cost_lines_shipment_id"),
        table_name="landed_cost_lines",
        schema="tenant",
    )
    op.drop_table("landed_cost_lines", schema="tenant")

    op.drop_index(
        op.f("ix_tenant_import_shipments_shipment_ref"),
        table_name="import_shipments",
        schema="tenant",
    )
    op.drop_table("import_shipments", schema="tenant")
