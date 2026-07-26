"""add_sequences_audit_hash

Revision ID: f3a8c91d4e72
Revises: 93012ca95668
Create Date: 2026-07-26 12:35:00.000000+00:00

Adds:
  1. document_sequences table — gapless per-(doc_type, branch_id, fiscal_year) counter
  2. audit_logs table — append-only immutable audit trail
  3. sequence_no column on journal_entries — populated at post time
  4. PostgreSQL RULE objects that make audit_logs physically un-updatable / un-deletable
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8c91d4e72"
down_revision: str | None = "93012ca95668"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_schema() -> str:
    """
    Retrieve the target schema name from the alembic context.
    In the tenant env.py, context.configure() sets version_table_schema
    to the actual schema name (e.g. "tenant_abc123"). We read it back
    from the migration context's config so we can inject the correct
    schema name into raw SQL (CREATE RULE, etc.).
    """
    from alembic import context as alembic_context
    schema = alembic_context.get_context().version_table_schema
    if not schema:
        raise RuntimeError(
            "Schema not found in Alembic context. "
            "Pass -x schema=<name> when running tenant migrations.",
        )
    return schema


def upgrade() -> None:
    # ── 1. document_sequences ─────────────────────────────────────────────────
    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doc_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("prefix", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default=""),
        sa.Column("padding", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "doc_type", "branch_id", "fiscal_year",
            name="uq_doc_seq_type_branch_year",
        ),
        schema="tenant",
    )
    op.create_index(
        "ix_document_sequences_branch_id", "document_sequences",
        ["branch_id"], unique=False, schema="tenant",
    )

    # ── 2. audit_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False, server_default="user"),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("entity_type", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("ui", "api", "ai_assisted", "system_event", "import", name="auditsource", schema="tenant"),
            nullable=False,
            server_default="api",
        ),
        sa.Column("ip_address", sqlmodel.sql.sqltypes.AutoString(length=45), nullable=True),
        sa.Column("user_agent", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"], unique=False, schema="tenant")
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_id"], unique=False, schema="tenant")
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["created_at"], unique=False, schema="tenant")

    # ── 3. sequence_no on journal_entries ─────────────────────────────────────
    op.add_column(
        "journal_entries",
        sa.Column("sequence_no", sa.Integer(), nullable=True),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_journal_entries_sequence_no"),
        "journal_entries",
        ["sequence_no"],
        unique=False,
        schema="tenant",
    )

    # ── 4. PostgreSQL RULE objects — physical immutability for audit_logs ──────
    # CRITICAL: These RULEs make it physically impossible to UPDATE or DELETE rows
    # in audit_logs, even as a superuser, without first explicitly dropping the rules.
    # Dropping the rules is itself a DDL event logged by PostgreSQL's own log.
    schema = _get_schema()
    op.execute(
        sa.text(
            f"CREATE RULE audit_no_update AS ON UPDATE TO {schema}.audit_logs "
            f"DO INSTEAD NOTHING",
        ),
    )
    op.execute(
        sa.text(
            f"CREATE RULE audit_no_delete AS ON DELETE TO {schema}.audit_logs "
            f"DO INSTEAD NOTHING",
        ),
    )


def downgrade() -> None:
    schema = _get_schema()

    # Drop rules before dropping the table
    op.execute(sa.text(f"DROP RULE IF EXISTS audit_no_delete ON {schema}.audit_logs"))
    op.execute(sa.text(f"DROP RULE IF EXISTS audit_no_update ON {schema}.audit_logs"))

    op.drop_index(
        op.f("ix_tenant_journal_entries_sequence_no"),
        table_name="journal_entries",
        schema="tenant",
    )
    op.drop_column("journal_entries", "sequence_no", schema="tenant")

    op.drop_index("ix_audit_logs_occurred_at", table_name="audit_logs", schema="tenant")
    op.drop_index("ix_audit_logs_actor", table_name="audit_logs", schema="tenant")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs", schema="tenant")
    op.drop_table("audit_logs", schema="tenant")

    op.drop_index("ix_document_sequences_branch_id", table_name="document_sequences", schema="tenant")
    op.drop_table("document_sequences", schema="tenant")
