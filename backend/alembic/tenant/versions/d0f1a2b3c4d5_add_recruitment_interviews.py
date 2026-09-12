"""add_recruitment_interviews

Revision ID: d0f1a2b3c4d5
Revises: c9e0f1a2b3c4
Create Date: 2026-09-10 00:10:00.000000+00:00

Recruitment Readiness Wave — Interview scheduling table. Idempotent: checks
table existence before DDL, same defensive pattern used throughout this
migration chain.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "d0f1a2b3c4d5"
down_revision: Union[str, None] = "c9e0f1a2b3c4"
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

    if not _table_exists("recruitment_interviews"):
        op.create_table(
            "recruitment_interviews",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column("job_order_id", sa.Uuid(), nullable=True),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("interviewer_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("location", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("result", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default="PENDING"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["case_id"], [f"{real_schema}.cases.id"],
                name="fk_recruitment_interviews_case_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["job_order_id"], [f"{real_schema}.recruitment_job_orders.id"],
                name="fk_recruitment_interviews_job_order_id",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_interviews_case", "recruitment_interviews",
            ["case_id"], schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_interviews_result", "recruitment_interviews",
            ["result"], schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_interviews_scheduled_at", "recruitment_interviews",
            ["scheduled_at"], schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_interviews_job_order_id", "recruitment_interviews",
            ["job_order_id"], schema=real_schema,
        )


def downgrade() -> None:
    real_schema = _get_real_schema()

    if _table_exists("recruitment_interviews"):
        op.drop_index("ix_recruitment_interviews_job_order_id", "recruitment_interviews", schema=real_schema)
        op.drop_index("ix_recruitment_interviews_scheduled_at", "recruitment_interviews", schema=real_schema)
        op.drop_index("ix_recruitment_interviews_result", "recruitment_interviews", schema=real_schema)
        op.drop_index("ix_recruitment_interviews_case", "recruitment_interviews", schema=real_schema)
        op.drop_table("recruitment_interviews", schema=real_schema)
