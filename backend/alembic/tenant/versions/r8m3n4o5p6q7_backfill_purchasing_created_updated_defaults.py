"""backfill_purchasing_created_updated_defaults

Revision ID: r8m3n4o5p6q7
Revises: q7l2m3n4o5p6
Create Date: 2026-08-22 21:15:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed bug, immediately after q7l2m3n4o5p6 fixed the
`purchaseorderstatus` enum-type issue: `POST /api/v1/purchasing/orders`
still 500s, now with:

    asyncpg.exceptions.NotNullViolationError: null value in column
    "created_at" of relation "purchase_orders" violates not-null constraint
    DETAIL: Failing row contains (01a02bb5-..., null, null, PO-E7E2365C, ...).
    [SQL: INSERT INTO tenant_....purchase_orders (id, created_by,
    updated_by, deleted_at, state, ..., status) VALUES (...) RETURNING
    tenant_....purchase_orders.created_at, tenant_....purchase_orders.updated_at]

The INSERT's column list omits created_at/updated_at entirely and asks for
them back via RETURNING — the standard SQLAlchemy pattern for a column
whose ORM-side declaration relies on a Postgres server_default (here,
BaseMixin in app/core/db/base.py: `sa_column_kwargs={"server_default":
func.now(), ...}` on both columns, applied to every TenantBase model
including PurchaseOrder). That only works if the DB column actually HAS
that default.

Root cause, confirmed by re-reading e5f6a1b2c3d4_phase_4b_purchasing.py
column-by-column: ALL FOUR tables it creates
(purchase_orders, purchase_order_lines, goods_receipts,
goods_receipt_lines) declare created_at/updated_at as plain
`sa.Column(..., sa.DateTime(), nullable=False)` with NO server_default —
unlike every other table in this codebase built on BaseMixin, which
consistently uses `server_default=sa.text("now()")` for these two columns
(see e.g. o5j0k1l2m3n4's `pos_cash_shifts` create_table, and the fix
pattern in e8f9a0b1c2d3_backfill_basemixin_audit_columns.py).

This gap was NOT caught by either prior backfill pass that touched these
same four tables:
  - e8f9a0b1c2d3_backfill_basemixin_audit_columns.py only backfilled
    created_by/updated_by/deleted_at for a different table list
    (egs_codes, vendor_bills, vendor_bill_lines,
    three_way_match_results) — it never touched purchase_orders et al.
  - o5j0k1l2m3n4_backfill_purchasing_audit_cols_and_pos.py DID target
    exactly these four tables, but its own docstring explicitly (and, it
    turns out, incorrectly) assumed created_at/updated_at were fine on all
    four ("these tables already have created_at/updated_at from their
    original CREATE TABLE, so only these three [created_by/updated_by/
    deleted_at] are ever actually missing") — it backfilled the three
    audit columns but never checked whether created_at/updated_at
    actually had a server_default, only that the columns existed.

So every one of the four purchasing tables has had NOT-NULL
created_at/updated_at with no default since e5f6a1b2c3d4 first shipped.
purchase_orders is the one caught live (POST .../orders is the first
purchasing write path exercised); purchase_order_lines is written in the
very same request (PurchaseOrder.lines is a selectin-loaded, cascading
child collection created alongside the parent), so it would have 500'd
immediately after purchase_orders was fixed alone. goods_receipts and
goods_receipt_lines share the identical original DDL gap and would hit the
exact same NotNullViolationError the first time a goods-receipt write path
is exercised — fixed here proactively rather than waiting for a fourth
live surprise.

Defensive/idempotent throughout, same helper pattern as every other
backfill migration in this chain (checks the column's current
`information_schema.columns.column_default` before altering — see
p6k1l2m3n4o5) — safe to re-run, safe for a tenant that already has these
defaults via some other path.

OTHER MISMATCHES FOUND BUT NOT FIXED HERE (flagged for a follow-up
decision, not blocking the current live 500):
  - `purchase_orders.state` and `goods_receipts.state`: DocumentLifecycleMixin
    declares `state` as `sa.Enum(DocumentState, name="documentstate",
    schema="tenant", create_type=False)` (app/core/models/mixins.py) — the
    `documentstate` enum type DOES exist (created by
    d4e5f6a1b2c3_phase_4a_approvals.py and used correctly by
    ddecea2865fa's tables), but e5f6a1b2c3d4 created both `state` columns as
    plain `sa.String(length=50)`, never converted to the enum type. Same
    class of bug as `purchaseorderstatus` (fixed in q7l2m3n4o5p6) — an
    INSERT/UPDATE that lets SQLAlchemy emit its usual
    `$N::tenant.documentstate` cast for `state` would fail with "column
    state is of type character varying but expression is of type
    tenant.documentstate". Did not fail on this request, so left un-fixed
    pending confirmation this is actually hit (possible it isn't, if some
    driver-level path avoids the explicit cast) — but worth a deliberate
    look before it surfaces live.
  - `goods_receipts.status`: same pattern again — GoodsReceipt model
    declares `sa.Enum(GoodsReceiptStatus, name="goodsreceiptstatus",
    schema="tenant")` but e5f6a1b2c3d4 created the column as plain
    `sa.String(length=50)` and no migration has ever created a
    `goodsreceiptstatus` type (confirmed via search — no CREATE TYPE for
    that name anywhere in backend/alembic/tenant/versions/). Untested live
    since no goods-receipt write path has been exercised yet; would 500
    the same way `purchaseorderstatus` did.
  - `purchase_orders.total_amount`: migration gives it
    `server_default="0.0000"`, but the model
    (app/modules/purchasing/models/core.py) does not mirror that
    server_default on its `sa_column` — not currently blocking (the model
    has a Python-side `default=Decimal("0.0000")` so every INSERT already
    supplies a value), just a drift worth noting.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "r8m3n4o5p6q7"
down_revision: Union[str, None] = "q7l2m3n4o5p6"
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


def _column_default(conn, schema: str, table: str, column: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()


def _ensure_now_default(conn, schema: str, table: str, column: str) -> None:
    if not _column_exists(conn, schema, table, column):
        # Column itself doesn't exist here — out of scope for this
        # migration (would have been caught by an earlier migration).
        return
    if _column_default(conn, schema, table, column) is None:
        op.alter_column(
            table,
            column,
            server_default=sa.text("now()"),
            schema="tenant",
        )


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    for table in (
        "purchase_orders",
        "purchase_order_lines",
        "goods_receipts",
        "goods_receipt_lines",
    ):
        if not _table_exists(conn, schema, table):
            continue
        _ensure_now_default(conn, schema, table, "created_at")
        _ensure_now_default(conn, schema, table, "updated_at")


def downgrade() -> None:
    # Not reversible — see p6k1l2m3n4o5/o5j0k1l2m3n4/e8f9a0b1c2d3 for the
    # same rationale: these defaults should have existed since the tables
    # were first created (every other BaseMixin-derived table has them);
    # removing them would just reintroduce the live 500.
    pass
