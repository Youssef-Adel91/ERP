"""Wave 3 item 1: Customer (Sales) Payments and Payment Allocations tables

Mirrors h8c3d4e5f6g7_phase_4b_step4_payments.py's supplier_payments /
payment_allocations shape, on the Accounts Receivable side. No FX columns —
sales payments are recorded in the invoice's own currency only.

Revision ID: y5t0u1v2w3x4
Revises: x4s9t0u1v2w3
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "y5t0u1v2w3x4"
down_revision: Union[str, None] = "x4s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. sales_payments
    op.create_table(
        "sales_payments",
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
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("treasury_id", sa.Uuid(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=20), server_default="CASH", nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="EGP", nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_sales_payments_payment_number"),
        "sales_payments",
        ["payment_number"],
        unique=True,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_sales_payments_contact_id"),
        "sales_payments",
        ["contact_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_sales_payments_treasury_id"),
        "sales_payments",
        ["treasury_id"],
        unique=False,
        schema="tenant",
    )

    # 2. sales_payment_allocations
    op.create_table(
        "sales_payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["tenant.sales_payments.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["tenant.sales_invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_sales_payment_allocations_payment_id"),
        "sales_payment_allocations",
        ["payment_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_sales_payment_allocations_invoice_id"),
        "sales_payment_allocations",
        ["invoice_id"],
        unique=False,
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tenant_sales_payment_allocations_invoice_id"),
        table_name="sales_payment_allocations",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_sales_payment_allocations_payment_id"),
        table_name="sales_payment_allocations",
        schema="tenant",
    )
    op.drop_table("sales_payment_allocations", schema="tenant")

    op.drop_index(
        op.f("ix_tenant_sales_payments_treasury_id"),
        table_name="sales_payments",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_sales_payments_contact_id"),
        table_name="sales_payments",
        schema="tenant",
    )
    op.drop_index(
        op.f("ix_tenant_sales_payments_payment_number"),
        table_name="sales_payments",
        schema="tenant",
    )
    op.drop_table("sales_payments", schema="tenant")
