"""Phase 4b Step 4: Supplier Payments and FX Realization tables

Revision ID: h8c3d4e5f6g7
Revises: g7b2c3d4e5f6
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h8c3d4e5f6g7"
down_revision: Union[str, None] = "g7b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. supplier_payments
    op.create_table(
        "supplier_payments",
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
        sa.Column("payment_number", sa.String(length=50), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("treasury_id", sa.Uuid(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), server_default="1.000000", nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
        sa.Column("fx_gain_loss_amount", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_supplier_payments_payment_number"),
        "supplier_payments",
        ["payment_number"],
        unique=True,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_supplier_payments_supplier_id"),
        "supplier_payments",
        ["supplier_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_supplier_payments_treasury_id"),
        "supplier_payments",
        ["treasury_id"],
        unique=False,
        schema="tenant",
    )

    # 2. payment_allocations
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["tenant.supplier_payments.id"]),
        sa.ForeignKeyConstraint(["bill_id"], ["tenant.vendor_bills.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_payment_allocations_payment_id"),
        "payment_allocations",
        ["payment_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_payment_allocations_bill_id"),
        "payment_allocations",
        ["bill_id"],
        unique=False,
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tenant_payment_allocations_bill_id"),
        table_name="payment_allocations",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_payment_allocations_payment_id"),
        table_name="payment_allocations",
        schema="tenant",
    )
    op.drop_table("payment_allocations", schema="tenant")

    op.drop_index(
        op.f("ix_tenant_supplier_payments_treasury_id"),
        table_name="supplier_payments",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_supplier_payments_supplier_id"),
        table_name="supplier_payments",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_supplier_payments_payment_number"),
        table_name="supplier_payments",
        schema="tenant",
    )
    op.drop_table("supplier_payments", schema="tenant")
