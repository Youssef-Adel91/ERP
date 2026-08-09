"""phase_4a_approvals

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-07-28 22:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a1b2c3'
down_revision: Union[str, None] = 'c3d4e5f6a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create Core Approval Tables (schema="tenant") ──────────────────────
    op.create_table(
        "approval_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("condition_field", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column(
            "operator",
            sa.Enum("GT", "GTE", "LT", "LTE", "EQ", "IN", "NOT_IN", name="ruleoperator", schema="tenant"),
            nullable=False,
        ),
        sa.Column("condition_value", sa.JSON(), nullable=True),
        sa.Column(
            "approver_type",
            sa.Enum("SPECIFIC_USER", "ROLE", "CREATOR_MANAGER", "APPROVAL_GROUP", name="approvertype", schema="tenant"),
            nullable=False,
        ),
        sa.Column("approver_ref", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        op.f("ix_tenant_approval_rules_document_type"),
        "approval_rules",
        ["document_type"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        "ix_approval_rules_doc_type_active",
        "approval_rules",
        ["document_type", "is_active"],
        unique=False,
        schema="tenant",
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_content_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column(
            "state",
            sa.Enum("PENDING", "APPROVED", "REJECTED", "WITHDRAWN", "ESCALATED", "EXPIRED", name="approvalrequeststate", schema="tenant"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("rule_version", sa.Integer(), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolution_comment", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("delegated_from_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["tenant.approval_rules.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        "ix_approval_requests_doc",
        "approval_requests",
        ["document_type", "document_id"],
        unique=False,
        schema="tenant",
    )

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum("APPROVE", "REJECT", name="decisiontype", schema="tenant"),
            nullable=False,
        ),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("comment", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("document_content_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("ip_address", sqlmodel.sql.sqltypes.AutoString(length=45), nullable=True),
        sa.Column("user_agent", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_request_id"], ["tenant.approval_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tenant",
    )
    op.create_index(
        "ix_approval_decisions_req",
        "approval_decisions",
        ["approval_request_id"],
        unique=False,
        schema="tenant",
    )
    op.create_index(
        "ix_approval_decisions_decider",
        "approval_decisions",
        ["decided_by"],
        unique=False,
        schema="tenant",
    )

    # ── 2. Expand: Add Universal Lifecycle Columns as Nullable First ──────────
    # Create the documentstate enum type in the tenant schema first
    op.execute(
        "CREATE TYPE tenant.documentstate AS ENUM ("
        "'DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'POSTED', "
        "'REJECTED', 'CANCELLED', 'WITHDRAWN', 'REVERSED', 'CLOSED'"
        ")"
    )
    doc_state_enum = sa.Enum(
        "DRAFT", "PENDING_APPROVAL", "APPROVED", "POSTED", "REJECTED",
        "CANCELLED", "WITHDRAWN", "REVERSED", "CLOSED",
        name="documentstate",
        schema="tenant",
        create_type=False,
    )

    for table_name in ("sales_invoices", "sales_returns", "journal_entries"):
        op.add_column(table_name, sa.Column("state", doc_state_enum, nullable=True), schema="tenant")
        op.add_column(table_name, sa.Column("content_hash", sa.String(length=64), nullable=True), schema="tenant")
        op.add_column(table_name, sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True), schema="tenant")
        op.add_column(table_name, sa.Column("submitted_by", sa.Uuid(), nullable=True), schema="tenant")
        op.add_column(table_name, sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), schema="tenant")
        if table_name != "journal_entries":
            # journal_entries already has posted_at column
            op.add_column(table_name, sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True), schema="tenant")
        op.add_column(table_name, sa.Column("reversal_of_id", sa.Uuid(), nullable=True), schema="tenant")
        op.create_index(f"ix_tenant_{table_name}_content_hash", table_name, ["content_hash"], unique=False, schema="tenant")
        op.create_index(f"ix_tenant_{table_name}_submitted_by", table_name, ["submitted_by"], unique=False, schema="tenant")
        op.create_index(f"ix_tenant_{table_name}_reversal_of_id", table_name, ["reversal_of_id"], unique=False, schema="tenant")

    # ── 3. Backfill: Populate state column from existing status values ────────
    op.execute("UPDATE tenant.sales_invoices SET state = 'POSTED' WHERE UPPER(CAST(status AS text)) IN ('POSTED', 'PAID')")
    op.execute("UPDATE tenant.sales_invoices SET state = 'DRAFT' WHERE state IS NULL")

    op.execute("UPDATE tenant.sales_returns SET state = 'POSTED' WHERE UPPER(CAST(status AS text)) IN ('RECEIVED', 'CREDITED', 'POSTED')")
    op.execute("UPDATE tenant.sales_returns SET state = 'DRAFT' WHERE state IS NULL")

    op.execute("UPDATE tenant.journal_entries SET state = 'POSTED' WHERE UPPER(CAST(status AS text)) = 'POSTED'")
    op.execute("UPDATE tenant.journal_entries SET state = 'CANCELLED' WHERE UPPER(CAST(status AS text)) IN ('VOIDED', 'VOID')")
    op.execute("UPDATE tenant.journal_entries SET state = 'DRAFT' WHERE state IS NULL")


def downgrade() -> None:
    for table_name in ("journal_entries", "sales_returns", "sales_invoices"):
        op.drop_index(f"ix_tenant_{table_name}_reversal_of_id", table_name=table_name, schema="tenant")
        op.drop_index(f"ix_tenant_{table_name}_submitted_by", table_name=table_name, schema="tenant")
        op.drop_index(f"ix_tenant_{table_name}_content_hash", table_name=table_name, schema="tenant")
        op.drop_column(table_name, "reversal_of_id", schema="tenant")
        if table_name != "journal_entries":
            op.drop_column(table_name, "posted_at", schema="tenant")
        op.drop_column(table_name, "approved_at", schema="tenant")
        op.drop_column(table_name, "submitted_by", schema="tenant")
        op.drop_column(table_name, "submitted_at", schema="tenant")
        op.drop_column(table_name, "content_hash", schema="tenant")
        op.drop_column(table_name, "state", schema="tenant")

    op.drop_index("ix_approval_decisions_decider", table_name="approval_decisions", schema="tenant")
    op.drop_index("ix_approval_decisions_req", table_name="approval_decisions", schema="tenant")
    op.drop_table("approval_decisions", schema="tenant")

    op.drop_index("ix_approval_requests_doc", table_name="approval_requests", schema="tenant")
    op.drop_table("approval_requests", schema="tenant")

    op.drop_index("ix_approval_rules_doc_type_active", table_name="approval_rules", schema="tenant")
    op.drop_index(op.f("ix_tenant_approval_rules_document_type"), table_name="approval_rules", schema="tenant")
    op.drop_table("approval_rules", schema="tenant")

    # Drop the documentstate enum type
    op.execute("DROP TYPE IF EXISTS tenant.documentstate")
