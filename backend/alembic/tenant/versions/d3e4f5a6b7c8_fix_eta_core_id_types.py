"""fix_eta_core_id_types

Revision ID: d3e4f5a6b7c8
Revises: c7d8e9f0a1b2
Create Date: 2026-08-09 00:10:00.000000+00:00

WHY THIS EXISTS:
Migration i9d4e5f6g7h8 (Phase 5 Step 2: ETA Core Models) created
eta_tenant_configs, eta_documents and eta_submissions with
id / created_by / updated_by / tenant_id columns typed as
sa.String(length=32), and created_at/updated_at as sa.DateTime()
(no timezone). The actual models (app/modules/eta/models/core.py) inherit
from TenantBase, whose BaseMixin declares:
    id: UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    created_at / updated_at: DateTime(timezone=True)
    created_by / updated_by: UUID | None
and EtaTenantConfig/EtaDocument/EtaSubmission.tenant_id: UUID.

This id-type mismatch (VARCHAR(32) in Postgres vs. Python uuid.UUID bound
by SQLAlchemy's native Uuid type) is what's been causing 500s ("invalid
input for query argument" / asyncpg encode errors) on every /eta/config
and /eta/documents endpoint.

DEFENSIVE BY DESIGN: some tenant schemas may have already had these three
tables created out-of-band by an ad-hoc `TenantBase.metadata.create_all()`
script (bypassing Alembic) using the CURRENT — already-correct — model
definitions. This migration must not assume a particular starting state:
  - table missing entirely            -> create fresh with correct types
  - table exists, id column is uuid   -> already correct, leave alone
  - table exists, id column is varchar -> drop (whatever indexes actually
    exist, discovered dynamically — do not assume fixed index names) and
    recreate with correct types
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_schema() -> str:
    from alembic import context as alembic_context
    schema = alembic_context.get_context().version_table_schema
    if not schema:
        raise RuntimeError(
            "Schema not found in Alembic context. "
            "Pass -x schema=<name> when running tenant migrations.",
        )
    return schema


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    ).scalar())


def _id_column_type(conn, schema: str, table: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = 'id'"
        ),
        {"schema": schema, "table": table},
    ).scalar()


def _drop_all_indexes(conn, schema: str, table: str) -> None:
    rows = conn.execute(
        sa.text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table "
            "AND indexname NOT LIKE '%_pkey'"
        ),
        {"schema": schema, "table": table},
    ).fetchall()
    for (idx_name,) in rows:
        conn.execute(sa.text(f'DROP INDEX IF EXISTS "{schema}"."{idx_name}"'))


def _create_eta_tenant_configs() -> None:
    op.create_table(
        "eta_tenant_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        "eta_tenant_configs", ["tenant_id"], unique=True, schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_tenant_configs_taxpayer_rin"),
        "eta_tenant_configs", ["taxpayer_rin"], unique=False, schema="tenant",
    )


def _create_eta_documents() -> None:
    op.create_table(
        "eta_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        "eta_documents", ["tenant_id"], unique=False, schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_internal_doc_id"),
        "eta_documents", ["internal_doc_id"], unique=False, schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_uuid"),
        "eta_documents", ["uuid"], unique=False, schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_submission_uuid"),
        "eta_documents", ["submission_uuid"], unique=False, schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_documents_state"),
        "eta_documents", ["state"], unique=False, schema="tenant",
    )


def _create_eta_submissions() -> None:
    op.create_table(
        "eta_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
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
        "eta_submissions", ["tenant_id"], unique=False, schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_eta_submissions_submission_uuid"),
        "eta_submissions", ["submission_uuid"], unique=True, schema="tenant",
    )


def _fix_table(conn, schema: str, table: str, creator) -> None:
    if not _table_exists(conn, schema, table):
        creator()
        return
    id_type = _id_column_type(conn, schema, table)
    if id_type == "uuid":
        # Already correct (e.g. created directly from the current model by
        # an out-of-band create_all() run) — nothing to do.
        return
    # Wrong type (varchar from the original buggy migration) — rebuild.
    _drop_all_indexes(conn, schema, table)
    op.drop_table(table, schema="tenant")
    creator()


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # Order matters for indexes but these three tables have no FKs between
    # them, so any order is safe.
    _fix_table(conn, schema, "eta_submissions", _create_eta_submissions)
    _fix_table(conn, schema, "eta_documents", _create_eta_documents)
    _fix_table(conn, schema, "eta_tenant_configs", _create_eta_tenant_configs)


def downgrade() -> None:
    # Not reversible to the old (broken) String(32) schema on purpose —
    # that schema was never functionally correct. Downgrade just drops
    # whatever exists now.
    conn = op.get_bind()
    schema = _get_schema()
    for table in ("eta_submissions", "eta_documents", "eta_tenant_configs"):
        if _table_exists(conn, schema, table):
            _drop_all_indexes(conn, schema, table)
            op.drop_table(table, schema="tenant")
