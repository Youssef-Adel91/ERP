"""add_recruitment_candidates

Revision ID: c9e0f1a2b3c4
Revises: b7389da6f618
Create Date: 2026-09-10 00:00:00.000000+00:00

Recruitment Readiness Wave — structured Candidate profile table.

One row per candidate Case (1:1 — case_id UNIQUE), works alongside the
existing free-form Case.data fields. Idempotent: checks table existence
before DDL, same defensive pattern as
A1b2c3d4e5f6_add_travel_passengers_visa_docs.py.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op


revision: str = "c9e0f1a2b3c4"
down_revision: Union[str, None] = "b7389da6f618"
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

    if not _table_exists("recruitment_candidates"):
        op.create_table(
            "recruitment_candidates",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column("full_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("full_name_ar", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("passport_number", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
            sa.Column("passport_expiry", sa.Date(), nullable=True),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("nationality", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column("gender", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
            sa.Column("profession", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
            sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
            sa.Column("expected_salary", sa.Numeric(18, 4), nullable=True),
            sa.Column("availability_status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default="AVAILABLE"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["case_id"], [f"{real_schema}.cases.id"],
                name="fk_recruitment_candidates_case_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("case_id", name="uq_recruitment_candidates_case"),
            schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_candidates_profession", "recruitment_candidates",
            ["profession"], schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_candidates_availability", "recruitment_candidates",
            ["availability_status"], schema=real_schema,
        )
        op.create_index(
            "ix_recruitment_candidates_case_id", "recruitment_candidates",
            ["case_id"], schema=real_schema,
        )


def downgrade() -> None:
    real_schema = _get_real_schema()

    if _table_exists("recruitment_candidates"):
        op.drop_index("ix_recruitment_candidates_case_id", "recruitment_candidates", schema=real_schema)
        op.drop_index("ix_recruitment_candidates_availability", "recruitment_candidates", schema=real_schema)
        op.drop_index("ix_recruitment_candidates_profession", "recruitment_candidates", schema=real_schema)
        op.drop_table("recruitment_candidates", schema=real_schema)
