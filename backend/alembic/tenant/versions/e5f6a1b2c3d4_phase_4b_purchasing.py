"""phase_4b_purchasing

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-07-29 01:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "e5f6a1b2c3d4"
down_revision: Union[str, None] = "d4e5f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create Purchase Orders Table ───────────────────────────────────────
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("po_number", sa.String(length=50), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EGP"),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=False, server_default="1.0000"),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="DRAFT"),
        # DocumentLifecycleMixin columns
        sa.Column("state", sa.String(length=50), nullable=False, server_default="DRAFT"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_orders_id"),
        "purchase_orders",
        ["id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_orders_po_number"),
        "purchase_orders",
        ["po_number"],
        unique=True,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_orders_supplier_id"),
        "purchase_orders",
        ["supplier_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_orders_warehouse_id"),
        "purchase_orders",
        ["warehouse_id"],
        unique=False,
        schema="tenant",
    )

    # ── 2. Create Purchase Order Lines Table ──────────────────────────────────
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("po_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("qty_ordered", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("qty_received", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("qty_billed", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("expected_landed_unit_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.ForeignKeyConstraint(["po_id"], ["tenant.purchase_orders.id"], ondelete="CASCADE"),
        sa.CheckConstraint("qty_received <= qty_ordered", name="ck_po_line_qty_received_le_ordered"),
        sa.CheckConstraint("qty_ordered >= 0", name="ck_po_line_qty_ordered_non_neg"),
        sa.CheckConstraint("qty_received >= 0", name="ck_po_line_qty_received_non_neg"),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_order_lines_id"),
        "purchase_order_lines",
        ["id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_order_lines_po_id"),
        "purchase_order_lines",
        ["po_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_purchase_order_lines_item_id"),
        "purchase_order_lines",
        ["item_id"],
        unique=False,
        schema="tenant",
    )

    # ── 3. Create Goods Receipts Table ────────────────────────────────────────
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("po_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("grn_number", sa.String(length=50), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_delivery_ref", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="DRAFT"),
        # DocumentLifecycleMixin columns
        sa.Column("state", sa.String(length=50), nullable=False, server_default="DRAFT"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["po_id"], ["tenant.purchase_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_goods_receipts_id"),
        "goods_receipts",
        ["id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_goods_receipts_grn_number"),
        "goods_receipts",
        ["grn_number"],
        unique=True,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_goods_receipts_po_id"),
        "goods_receipts",
        ["po_id"],
        unique=False,
        schema="tenant",
    )

    # ── 4. Create Goods Receipt Lines Table ───────────────────────────────────
    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("grn_id", sa.Uuid(), nullable=False),
        sa.Column("po_line_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("qty_received", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("qty_rejected", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("serial_ids", sa.JSON(), nullable=True),
        sa.Column("unit_cost_estimated", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.ForeignKeyConstraint(["grn_id"], ["tenant.goods_receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["po_line_id"], ["tenant.purchase_order_lines.id"], ondelete="SET NULL"),
        sa.CheckConstraint("qty_received >= 0", name="ck_grn_line_qty_received_non_neg"),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_goods_receipt_lines_id"),
        "goods_receipt_lines",
        ["id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_goods_receipt_lines_grn_id"),
        "goods_receipt_lines",
        ["grn_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_goods_receipt_lines_po_line_id"),
        "goods_receipt_lines",
        ["po_line_id"],
        unique=False,
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_table("goods_receipt_lines", schema="tenant")
    op.drop_table("goods_receipts", schema="tenant")
    op.drop_table("purchase_order_lines", schema="tenant")
    op.drop_table("purchase_orders", schema="tenant")
