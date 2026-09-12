"""add_ai_drafted_messages

Revision ID: e1f2a3b4c5d6
Revises: d0f1a2b3c4d5
Create Date: 2026-09-11 17:10:00.000000+00:00

AI roadmap Level 4 (Agentic Document Drafting via the existing Approval
Engine — see app.modules.ai.models.AIDraftedMessage's module docstring).
Adopts DocumentLifecycleMixin, same "reuse the universal state machine and
tenant.documentstate enum type" pattern as
d4e5f6a1b2c3_phase_4a_approvals.py's purchase_order/goods_receipts columns
— that enum type already exists in every tenant schema from that earlier
migration, so this only ADDS two new enum types of its own
(aidraftpurpose, aidraftchannel) and references the existing documentstate
one with create_type=False (postgresql.ENUM, not generic sa.Enum — see the
cheque_type_enum precedent in c7d8e9f0a1b2_add_cheques_table.py for why).

Idempotent: checks table existence before DDL, same defensive pattern as
c9e0f1a2b3c4_add_recruitment_candidates.py.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_real_schema() -> str:
    bind = op.get_bind()
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar()
    if not schema or schema == "public":
        try:
            from alembic import context as _ctx
            schema = _ctx.get_x_argument(as_dictionary=True).get("schema", "tenant")
        except Exception:
            schema = "tenant"
    return schema


def _table_exists(table_name: str, schema: str | None = None) -> bool:
    bind = op.get_bind()
    real_schema = schema if schema is not None else _get_real_schema()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table_name"
            ),
            {"schema": real_schema, "table_name": table_name},
        ).scalar()
    )


def upgrade() -> None:
    real_schema = _get_real_schema()

    op.execute(f"""
        DO $$ BEGIN
            CREATE TYPE {real_schema}.aidraftpurpose AS ENUM ('overdue_payment_reminder');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute(f"""
        DO $$ BEGIN
            CREATE TYPE {real_schema}.aidraftchannel AS ENUM ('whatsapp');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    purpose_enum = postgresql.ENUM(
        "overdue_payment_reminder", name="aidraftpurpose", schema=real_schema, create_type=False,
    )
    channel_enum = postgresql.ENUM(
        "whatsapp", name="aidraftchannel", schema=real_schema, create_type=False,
    )
    doc_state_enum = postgresql.ENUM(
        "DRAFT", "PENDING_APPROVAL", "APPROVED", "POSTED", "REJECTED",
        "CANCELLED", "WITHDRAWN", "REVERSED", "CLOSED",
        name="documentstate",
        schema=real_schema,
        create_type=False,
    )

    if not _table_exists("ai_drafted_messages"):
        op.create_table(
            "ai_drafted_messages",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            # DocumentLifecycleMixin columns — same set/semantics as
            # sales_invoices/sales_returns/journal_entries/purchase_orders.
            sa.Column("state", doc_state_enum, nullable=False, server_default="DRAFT"),
            sa.Column("content_hash", sa.String(length=64), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("submitted_by", sa.Uuid(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
            # This model's own fields.
            sa.Column("purpose", purpose_enum, nullable=False),
            sa.Column("channel", channel_enum, nullable=False, server_default="whatsapp"),
            sa.Column("contact_id", sa.Uuid(), nullable=False),
            sa.Column("draft_text", sa.Text(), nullable=False),
            sa.Column("grounding_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("send_error", sa.String(length=500), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            schema=real_schema,
        )
        op.create_index(
            "ix_ai_drafted_messages_contact_id", "ai_drafted_messages",
            ["contact_id"], schema=real_schema,
        )
        op.create_index(
            "ix_ai_drafted_messages_content_hash", "ai_drafted_messages",
            ["content_hash"], schema=real_schema,
        )
        op.create_index(
            "ix_ai_drafted_messages_submitted_by", "ai_drafted_messages",
            ["submitted_by"], schema=real_schema,
        )
        op.create_index(
            "ix_ai_drafted_messages_reversal_of_id", "ai_drafted_messages",
            ["reversal_of_id"], schema=real_schema,
        )


def downgrade() -> None:
    real_schema = _get_real_schema()

    if _table_exists("ai_drafted_messages"):
        op.drop_index("ix_ai_drafted_messages_reversal_of_id", "ai_drafted_messages", schema=real_schema)
        op.drop_index("ix_ai_drafted_messages_submitted_by", "ai_drafted_messages", schema=real_schema)
        op.drop_index("ix_ai_drafted_messages_content_hash", "ai_drafted_messages", schema=real_schema)
        op.drop_index("ix_ai_drafted_messages_contact_id", "ai_drafted_messages", schema=real_schema)
        op.drop_table("ai_drafted_messages", schema=real_schema)

    op.execute(f"DROP TYPE IF EXISTS {real_schema}.aidraftchannel")
    op.execute(f"DROP TYPE IF EXISTS {real_schema}.aidraftpurpose")
