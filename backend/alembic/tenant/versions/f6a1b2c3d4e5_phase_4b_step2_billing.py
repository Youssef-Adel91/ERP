"""phase_4b_step2_billing

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-07-29 02:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create Vendor Bills Table ──────────────────────────────────────────
    op.create_table(
        "vendor_bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("bill_number", sa.String(length=50), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EGP"),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=False, server_default="1.000000"),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("match_state", sa.String(length=30), nullable=False, server_default="UNMATCHED"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("tax_total", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_number"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bills_bill_number"),
        "vendor_bills",
        ["bill_number"],
        unique=True,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bills_supplier_id"),
        "vendor_bills",
        ["supplier_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bills_branch_id"),
        "vendor_bills",
        ["branch_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bills_state"),
        "vendor_bills",
        ["state"],
        unique=False,
        schema="tenant",
    )

    # ── 2. Create Vendor Bill Lines Table ─────────────────────────────────────
    op.create_table(
        "vendor_bill_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("po_line_id", sa.Uuid(), nullable=True),
        sa.Column("grn_line_id", sa.Uuid(), nullable=True),
        sa.Column("qty_billed", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["bill_id"], ["tenant.vendor_bills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bill_lines_bill_id"),
        "vendor_bill_lines",
        ["bill_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bill_lines_po_line_id"),
        "vendor_bill_lines",
        ["po_line_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_vendor_bill_lines_grn_line_id"),
        "vendor_bill_lines",
        ["grn_line_id"],
        unique=False,
        schema="tenant",
    )

    # ── 3. Create Three-Way Match Results Table ───────────────────────────────
    op.create_table(
        "three_way_match_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("bill_line_id", sa.Uuid(), nullable=False),
        sa.Column("qty_variance", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("price_variance", sa.Numeric(precision=18, scale=4), nullable=False, server_default="0.0000"),
        sa.Column("is_within_tolerance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_three_way_match_results_bill_id"),
        "three_way_match_results",
        ["bill_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_three_way_match_results_bill_line_id"),
        "three_way_match_results",
        ["bill_line_id"],
        unique=False,
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_table("three_way_match_results", schema="tenant")
    op.drop_table("vendor_bill_lines", schema="tenant")
    op.drop_table("vendor_bills", schema="tenant")
