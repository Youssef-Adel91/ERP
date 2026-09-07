"""backfill_sales_payments_lifecycle_cols

Revision ID: a6v1w2x3y4z5
Revises: y5t0u1v2w3x4
Create Date: 2026-09-04 00:00:00.000000+00:00

WHY THIS EXISTS:
`DocumentLifecycleMixin` (app/core/models/mixins.py) defines two columns —
`posted_at` and `reversal_of_id` — that y5t0u1v2w3x4_add_sales_payments.py's
CREATE TABLE for `sales_payments` omitted (it was written by copying
h8c3d4e5f6g7_phase_4b_step4_payments.py's supplier_payments table shape,
which itself predates the mixin gaining those two fields and was never
backfilled for this exact reason on other tables — see
n4i9j0k1l2m3_backfill_lifecycle_cols_and_carriers.py, which fixed the same
class of bug for purchase_orders/goods_receipts/import_shipments).

Confirmed LIVE via a real authenticated request against the running app:
`GET /api/v1/sales/payments` -> 500
`asyncpg.exceptions.UndefinedColumnError: column sales_payments.posted_at
does not exist`.

Since y5t0u1v2w3x4 has already been applied (per this project's rule, an
already-applied migration file is never edited), this is a new, additive
migration that only adds the two missing columns. It reuses the exact same
idempotent existence-check helper pattern as
n4i9j0k1l2m3_backfill_lifecycle_cols_and_carriers.py, so it is safe to
re-run and safe for a tenant schema that already has these columns via a
different path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a6v1w2x3y4z5"
down_revision: Union[str, None] = "y5t0u1v2w3x4"
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

    for table in ("sales_payments",):
        _backfill_document_lifecycle_columns(conn, schema, table)


def downgrade() -> None:
    # Not reversible, same rationale as the migrations this one mirrors:
    # these columns should have existed since the table was first created;
    # removing them would just reintroduce the bug.
    pass
