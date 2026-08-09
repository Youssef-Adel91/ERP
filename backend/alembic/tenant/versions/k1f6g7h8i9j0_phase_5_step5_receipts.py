"""Phase 5 Step 5: ETA e-Receipts (B2C) & Batches

Revision ID: k1f6g7h8i9j0
Revises: j0e5f6g7h8i9
Create Date: 2026-07-31 03:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k1f6g7h8i9j0"
down_revision: Union[str, None] = "j0e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create eta_receipt_batches table ────────────────────────────────────
    op.create_table(
        "eta_receipt_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("pos_terminal_id", sa.String(length=100), nullable=False),
        sa.Column("receipt_ids", sa.JSON(), nullable=False),
        sa.Column("receipt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch_canonical_hash", sa.String(length=64), nullable=True),
        sa.Column("signature_b64", sa.Text(), nullable=True),
        sa.Column("submission_uuid", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_eta_receipt_batches"),
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipt_batches_tenant_id",
        "eta_receipt_batches",
        ["tenant_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipt_batches_pos_terminal_id",
        "eta_receipt_batches",
        ["pos_terminal_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipt_batches_submission_uuid",
        "eta_receipt_batches",
        ["submission_uuid"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipt_batches_state",
        "eta_receipt_batches",
        ["state"],
        schema="tenant",
    )

    # ── 2. Create eta_receipts table ───────────────────────────────────────────
    op.create_table(
        "eta_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("internal_doc_id", sa.String(length=100), nullable=False),
        sa.Column("receipt_number", sa.String(length=100), nullable=False),
        sa.Column("uuid", sa.String(length=100), nullable=True),
        sa.Column("previous_uuid", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("date_time_issued", sa.DateTime(timezone=True), nullable=False),
        sa.Column("late_on_arrival", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("qr_payload", sa.Text(), nullable=True),
        sa.Column("public_url", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_eta_receipts"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["tenant.eta_receipt_batches.id"],
            name="fk_eta_receipts_batch_id",
            ondelete="SET NULL",
        ),
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipts_tenant_id",
        "eta_receipts",
        ["tenant_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipts_batch_id",
        "eta_receipts",
        ["batch_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipts_internal_doc_id",
        "eta_receipts",
        ["internal_doc_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipts_receipt_number",
        "eta_receipts",
        ["receipt_number"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipts_uuid",
        "eta_receipts",
        ["uuid"],
        schema="tenant",
    )
    op.create_index(
        "ix_tenant_eta_receipts_state",
        "eta_receipts",
        ["state"],
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_table("eta_receipts", schema="tenant")
    op.drop_table("eta_receipt_batches", schema="tenant")
