"""backfill_purchasing_audit_cols_and_pos

Revision ID: o5j0k1l2m3n4
Revises: n4i9j0k1l2m3
Create Date: 2026-08-22 12:00:00.000000+00:00

WHY THIS EXISTS:
Live re-testing after n4i9j0k1l2m3 (which added posted_at/reversal_of_id to
purchase_orders/goods_receipts/import_shipments and created the carrier
tables) showed the carrier fix worked, but two other endpoints were STILL
500ing. Root-caused by re-reading every migration that has ever touched
these tables, column-by-column, against BaseMixin (app/core/db/base.py):

1. `GET /api/v1/purchasing/orders` -> 500 (still).
   `PurchaseOrder`/`GoodsReceipt`/`PurchaseOrderLine`/`GoodsReceiptLine` all
   inherit `TenantBase` -> `BaseMixin`, which declares FIVE audit columns:
   created_at, updated_at, created_by, updated_by, deleted_at. But their
   original CREATE TABLE (e5f6a1b2c3d4_phase_4b_purchasing.py) only ever
   included created_at/updated_at — created_by, updated_by, and deleted_at
   were never part of that table's DDL at all, for any of the four tables.

   This gap was NOT the same bug n4i9j0k1l2m3 fixed (that migration only
   backfilled DocumentLifecycleMixin's posted_at/reversal_of_id) and was
   NOT covered by e8f9a0b1c2d3_backfill_basemixin_audit_columns.py either —
   that migration's exact same class of fix (missing BaseMixin audit
   columns) was scoped only to `egs_codes`, `vendor_bills`,
   `vendor_bill_lines`, `three_way_match_results`. purchase_orders,
   goods_receipts, purchase_order_lines, and goods_receipt_lines were never
   in either list, so `select(PurchaseOrder)` (and the selectin-loaded
   `.lines`/`.receipts` relationships it triggers) still 500s with
   `asyncpg.exceptions.UndefinedColumnError: column purchase_orders.created_by
   does not exist` even after n4i9j0k1l2m3 is applied.

   Confirmed by direct column-list diff against e5f6a1b2c3d4's create_table
   calls: purchase_order_lines and goods_receipt_lines are missing all
   THREE of created_by/updated_by/deleted_at too (not just the parent
   documents), since PurchaseOrder.lines/GoodsReceipt.lines are
   `lazy="selectin"` and are always loaded alongside the parent.

   import_shipments/landed_cost_lines/landed_cost_allocations (created by
   g7b2c3d4e5f6_phase_4b_step3_landed_cost.py) already include all five
   BaseMixin audit columns from the start — confirmed by inspection — so
   they are intentionally NOT touched here.

2. `GET /api/v1/pos/shifts/current` -> 500 (still).
   `app/modules/pos/models.py` (CashShift) was NOT edited today, and the
   current content of 99f91dd227cd_add_missing_tenant_models.py DOES
   create `pos_cash_shifts` with a column list that matches the CashShift
   model exactly, including all five BaseMixin audit columns and the
   `shiftstatus` native enum.

   However 99f91dd227cd's file mtime shows it WAS edited today (it was
   modified in the same batch as this morning's other fixes, to make its
   `employeestatus` enum creation idempotent — see that file's own
   docstring), despite being an ALREADY-APPLIED revision for tenants
   created before today (its "Create Date" docstring says 2026-08-11, and
   at least one tenant is known to have successfully migrated past it back
   then). This is the exact same anti-pattern already diagnosed once in
   this repo (see f4a5b6c7d8e9's docstring: "any further edits to
   [an already-applied file]'s upgrade() body would never execute for this
   tenant — Alembic only runs upgrade() for revisions between the current
   stamp and head"). Whether `pos_cash_shifts` creation itself was part of
   today's edit to 99f91dd227cd or predates it could not be established
   from the file alone (no VCS history available in this checkout) — but
   given the file WAS touched today and the anti-pattern has bitten this
   exact codebase before, this migration defensively (idempotently)
   re-asserts `pos_cash_shifts` exists with the exact structure the
   CashShift model expects, for any tenant where — for whatever reason —
   it does not. Safe/no-op for tenants where it already does.

Defensive/idempotent throughout, same helper pattern as every other
backfill migration in this chain — safe to re-run, safe for a tenant that
already has some/all of these objects via a different path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "o5j0k1l2m3n4"
down_revision: Union[str, None] = "n4i9j0k1l2m3"
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


def _type_exists(conn, schema: str, type_name: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND t.typname = :type_name"
        ),
        {"schema": schema, "type_name": type_name},
    ).scalar())


# BaseMixin's audit columns — every TenantBase table needs all five, but
# these tables already have created_at/updated_at from their original
# CREATE TABLE, so only these three are ever actually missing.
_AUDIT_COLUMNS = [
    ("created_by", lambda: sa.Column("created_by", sa.Uuid(), nullable=True)),
    ("updated_by", lambda: sa.Column("updated_by", sa.Uuid(), nullable=True)),
    ("deleted_at", lambda: sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)),
]


def _backfill_audit_columns(conn, schema: str, table: str) -> None:
    if not _table_exists(conn, schema, table):
        return
    for col_name, col_factory in _AUDIT_COLUMNS:
        if not _column_exists(conn, schema, table, col_name):
            op.add_column(table, col_factory(), schema="tenant")


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Backfill BaseMixin audit columns missed by both e8f9a0b1c2d3
    #        (different table list) and n4i9j0k1l2m3 (different columns) ──
    for table in (
        "purchase_orders",
        "goods_receipts",
        "purchase_order_lines",
        "goods_receipt_lines",
    ):
        _backfill_audit_columns(conn, schema, table)

    # ── 2. Defensively re-assert pos_cash_shifts exists with the full
    #        structure CashShift expects (idempotent — see docstring) ────
    if not _type_exists(conn, schema, "shiftstatus"):
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE "tenant"."shiftstatus" AS ENUM ('OPEN', 'CLOSED');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    if not _table_exists(conn, schema, "pos_cash_shifts"):
        op.create_table(
            "pos_cash_shifts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("opened_by", sa.Uuid(), nullable=False),
            sa.Column("closed_by", sa.Uuid(), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM("OPEN", "CLOSED", name="shiftstatus", schema="tenant", create_type=False),
                nullable=False,
            ),
            sa.Column("opening_balance", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("closing_balance", sa.Numeric(precision=18, scale=4), nullable=True),
            sa.Column("expected_balance", sa.Numeric(precision=18, scale=4), nullable=True),
            sa.Column("variance", sa.Numeric(precision=18, scale=4), nullable=True),
            sa.Column("opened_at", sa.DateTime(), nullable=False),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_pos_cash_shifts_opened_by"), "pos_cash_shifts", ["opened_by"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_pos_cash_shifts_status"), "pos_cash_shifts", ["status"], unique=False, schema="tenant",
        )
    else:
        # Table exists (e.g. from the original 99f91dd227cd run) — make sure
        # it isn't itself missing an audit column via the same drift class
        # as section 1 above.
        _backfill_audit_columns(conn, schema, "pos_cash_shifts")


def downgrade() -> None:
    # Not reversible — see f4a5b6c7d8e9/e8f9a0b1c2d3/n4i9j0k1l2m3 for the
    # same rationale: these columns should have existed since the tables
    # were first created, and pos_cash_shifts should have existed since
    # 99f91dd227cd; removing either would just reintroduce the bug.
    pass
