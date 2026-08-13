"""backfill_basemixin_audit_columns

Revision ID: e8f9a0b1c2d3
Revises: ddecea2865fa
Create Date: 2026-08-09 23:40:00.000000+00:00

WHY THIS EXISTS:
Confirmed via a live traceback against the real tenant database
(tenant_1612bc36_7e63_42c1_add9_2d63cb81d976):

    asyncpg.exceptions.UndefinedColumnError: column egs_codes.created_at does not exist
    asyncpg.exceptions.UndefinedColumnError: column vendor_bills.created_by does not exist

Root cause, found by reading the ORIGINAL migration source (not a tenant-
specific drift issue — this affects every tenant that has run these two
migrations):

  - j0e5f6g7h8i9_phase_5_step3_egs_codes.py: the `egs_codes` create_table
    call never included ANY of the five BaseMixin audit columns
    (created_at, updated_at, created_by, updated_by, deleted_at) at all.

  - f6a1b2c3d4e5_phase_4b_step2_billing.py: `vendor_bills`,
    `vendor_bill_lines`, and `three_way_match_results` all include
    created_at/updated_at but are missing created_by, updated_by, and
    deleted_at. `vendor_bills` is additionally missing `reversal_of_id`,
    which DocumentLifecycleMixin declares on every document model.

Every SQLModel model built on TenantBase (via BaseMixin) declares these
columns unconditionally, so any SELECT * equivalent (SQLModel's default
`select(Model)`) 500s with UndefinedColumnError the moment it's run against
a schema created from the original migrations.

This migration is defensive (checks column existence before adding) so it
is safe to run against a tenant that already has a correct schema through
some other path, and safe to re-run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "ddecea2865fa"
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


# BaseMixin's audit columns — every TenantBase table needs all five.
_AUDIT_COLUMNS = [
    ("created_at", lambda: sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)),
    ("updated_at", lambda: sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)),
    ("created_by", lambda: sa.Column("created_by", sa.Uuid(), nullable=True)),
    ("updated_by", lambda: sa.Column("updated_by", sa.Uuid(), nullable=True)),
    ("deleted_at", lambda: sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)),
]


def _backfill_audit_columns(conn, schema: str, table: str) -> None:
    if not _table_exists(conn, schema, table):
        # Table itself doesn't exist here — out of scope for this migration
        # (would have been caught by an earlier migration in the chain).
        return
    for col_name, col_factory in _AUDIT_COLUMNS:
        if not _column_exists(conn, schema, table, col_name):
            op.add_column(table, col_factory(), schema="tenant")


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    for table in ("egs_codes", "vendor_bills", "vendor_bill_lines", "three_way_match_results"):
        _backfill_audit_columns(conn, schema, table)

    # vendor_bills is also missing DocumentLifecycleMixin's reversal_of_id.
    # (posted_at is handled by the follow-up migration f4a5b6c7d8e9, added
    # after this migration had already run against the tenant being
    # debugged — see that file's docstring for why it's separate.)
    if _table_exists(conn, schema, "vendor_bills") and not _column_exists(conn, schema, "vendor_bills", "reversal_of_id"):
        op.add_column(
            "vendor_bills",
            sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_vendor_bills_reversal_of_id"),
            "vendor_bills", ["reversal_of_id"], unique=False, schema="tenant",
        )


def downgrade() -> None:
    # Not reversible — these columns should have existed since the tables
    # were first created; removing them would just reintroduce the bug.
    pass
