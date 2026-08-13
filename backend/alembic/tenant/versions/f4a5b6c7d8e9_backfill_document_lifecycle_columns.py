"""backfill_document_lifecycle_columns

Revision ID: f4a5b6c7d8e9
Revises: e8f9a0b1c2d3
Create Date: 2026-08-09 23:45:00.000000+00:00

WHY THIS EXISTS AS A SEPARATE MIGRATION (not folded into e8f9a0b1c2d3):
The tenant this was diagnosed against has ALREADY run e8f9a0b1c2d3 (its
alembic_version is stamped past it), so any further edits to that file's
upgrade() body would never execute for this tenant — Alembic only runs
upgrade() for revisions between the current stamp and head. Confirmed via
live traceback after re-testing post-repair:

    asyncpg.exceptions.UndefinedColumnError: column vendor_bills.posted_at does not exist

Root cause (same class of bug as e8f9a0b1c2d3, found by reading the
original hand-written migrations again): every model using
DocumentLifecycleMixin (app/core/models/mixins.py) declares
posted_at and reversal_of_id, but:
  - f6a1b2c3d4e5_phase_4b_step2_billing.py (vendor_bills) omits both.
  - h8c3d4e5f6g7_phase_4b_step4_payments.py (supplier_payments) omits both
    too (not yet hit by a live error, but confirmed by inspection — fixing
    proactively rather than waiting for the next round-trip).

Defensive/idempotent: checks column existence before adding, safe to
re-run, safe for tenants that already have these columns via some other
path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
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


def _column_exists(conn, schema: str, table: str, column: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar())


def _index_exists(conn, schema: str, index_name: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE schemaname = :s AND indexname = :i"
        ),
        {"s": schema, "i": index_name},
    ).scalar())


def _backfill_document_lifecycle_columns(conn, schema: str, table: str) -> None:
    if not _table_exists(conn, schema, table):
        return
    if not _column_exists(conn, schema, table, "posted_at"):
        op.add_column(
            table,
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            schema="tenant",
        )
    if not _column_exists(conn, schema, table, "reversal_of_id"):
        op.add_column(
            table,
            sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
            schema="tenant",
        )
        idx_name = f"ix_tenant_{table}_reversal_of_id"
        if not _index_exists(conn, schema, idx_name):
            op.create_index(
                op.f(idx_name),
                table, ["reversal_of_id"], unique=False, schema="tenant",
            )


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    for table in ("vendor_bills", "supplier_payments"):
        _backfill_document_lifecycle_columns(conn, schema, table)


def downgrade() -> None:
    # Not reversible — these columns should have existed since the tables
    # were first created; removing them would just reintroduce the bug.
    pass
