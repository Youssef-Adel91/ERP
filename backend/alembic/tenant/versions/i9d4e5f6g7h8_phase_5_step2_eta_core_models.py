"""Phase 5 Step 2: ETA Core Models (EtaTenantConfig, EtaDocument, EtaSubmission)

Revision ID: i9d4e5f6g7h8
Revises: h8c3d4e5f6g7
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "i9d4e5f6g7h8"
down_revision: Union[str, None] = "h8c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. eta_tenant_configs
    op.create_table(
        "eta_tenant_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=20), server_default="PREPRODUCTION", nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_ref", sa.String(length=255), nullable=True),
        sa.Column("taxpayer_rin", sa.String(length=50), nullable=False),
        sa.Column("activity_code", sa.String(length=50), nullable=False),
        sa.Column("branch_eta_codes", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("signing_provider", sa.String(length=30), server_default="CLOUD_HSM", nullable=False),
        sa.Column("preflight_state", sa.String(length=30), server_default="UNVERIFIED", nullable=False),
        sa.Column("is_live", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("went_live_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_tenant_configs_tenant_id"),
        "eta_tenant_configs",
        ["tenant_id"],
        unique=True,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_tenant_configs_taxpayer_rin"),
        "eta_tenant_configs",
        ["taxpayer_rin"],
        unique=False,
        schema="tenant",
    )

    # 2. eta_documents
    op.create_table(
        "eta_documents",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("internal_doc_type", sa.String(length=50), nullable=False),
        sa.Column("internal_doc_id", sa.String(length=100), nullable=False),
        sa.Column("eta_document_type", sa.String(length=1), nullable=False),
        sa.Column("eta_document_type_version", sa.String(length=10), server_default="1.0", nullable=False),
        sa.Column("uuid", sa.String(length=100), nullable=True),
        sa.Column("long_id", sa.String(length=100), nullable=True),
        sa.Column("submission_uuid", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("canonical_string_hash", sa.String(length=64), nullable=True),
        sa.Column("signature_b64", sa.Text(), nullable=True),
        sa.Column("signature_type", sa.String(length=1), server_default="I", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("translated_errors", sa.JSON(), nullable=True),
        sa.Column("date_time_issued", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("public_url", sa.String(length=255), nullable=True),
        sa.Column("qr_payload", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_tenant_id"),
        "eta_documents",
        ["tenant_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_internal_doc_id"),
        "eta_documents",
        ["internal_doc_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_uuid"),
        "eta_documents",
        ["uuid"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_submission_uuid"),
        "eta_documents",
        ["submission_uuid"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_state"),
        "eta_documents",
        ["state"],
        unique=False,
        schema="tenant",
    )

    # 3. eta_submissions
    op.create_table(
        "eta_submissions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("submission_uuid", sa.String(length=100), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("document_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("callback_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_submissions_tenant_id"),
        "eta_submissions",
        ["tenant_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_submissions_submission_uuid"),
        "eta_submissions",
        ["submission_uuid"],
        unique=True,
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_eta_submissions_submission_uuid"), table_name="eta_submissions", schema="tenant")
    op.drop_index(op.f("ix_tenant_eta_submissions_tenant_id"), table_name="eta_submissions", schema="tenant")
    op.drop_table("eta_submissions", schema="tenant")

    op.drop_index(op.f("ix_tenant_eta_documents_state"), table_name="eta_documents", schema="tenant")
    op.drop_index(op.f("ix_tenant_eta_documents_submission_uuid"), table_name="eta_documents", schema="tenant")
    op.drop_index(op.f("ix_tenant_eta_documents_uuid"), table_name="eta_documents", schema="tenant")
    op.drop_index(op.f("ix_tenant_eta_documents_internal_doc_id"), table_name="eta_documents", schema="tenant")
    op.drop_index(op.f("ix_tenant_eta_documents_tenant_id"), table_name="eta_documents", schema="tenant")
    op.drop_table("eta_documents", schema="tenant")

    op.drop_index(op.f("ix_tenant_eta_tenant_configs_taxpayer_rin"), table_name="eta_tenant_configs", schema="tenant")
    op.drop_index(op.f("ix_tenant_eta_tenant_configs_tenant_id"), table_name="eta_tenant_configs", schema="tenant")
    op.drop_table("eta_tenant_configs", schema="tenant")
