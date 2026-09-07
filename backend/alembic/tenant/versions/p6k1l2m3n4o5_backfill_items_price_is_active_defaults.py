"""backfill_items_price_is_active_defaults

Revision ID: p6k1l2m3n4o5
Revises: o5j0k1l2m3n4
Create Date: 2026-08-22 18:00:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed bug: `POST /api/v1/inventory/items` (app/modules/inventory —
the current, live Item master-data endpoint, per main.py's "Cut over from
app.plugins.inventory (retired)" comment) 500s for every request with
`asyncpg.exceptions.NotNullViolationError: null value in column "price" of
relation "items" violates not-null constraint`.

Root cause, confirmed by reading both Item models and the full migration
history for `tenant.items`:

  - `app/modules/inventory/models/core.py`'s `Item` (the live model backing
    this endpoint) is a deliberately leaner rewrite — its own inline
    docstring/comments in app/modules/inventory/api/items.py say so
    explicitly: "models/core.py's Item has no name_ar / description /
    category / price / cost / quantity_on_hand / reorder_level / is_active
    columns [...] Pricing lives on ItemVariant, stock quantity lives in
    StockLevel". main.py's router wiring confirms this was an intentional
    cutover: "Item no longer carries price/cost/quantity_on_hand directly
    — see ItemVariant/StockLevel."
  - BUT the physical `tenant.items` table was never altered to match. It
    is still exactly the table `226439fee167_init_tenant.py` created for
    the old, retired `app/plugins/inventory.Item` model (full columns:
    name_ar, description, category, price, cost, quantity_on_hand,
    reorder_level, is_active, created_by, created_at) — f93809b48226 only
    ever ADDED columns to it (egs_code/costing_method/requires_batch/
    requires_serial), it never removed or relaxed any of the old ones.
  - Of those legacy columns, `cost`, `quantity_on_hand`, and `reorder_level`
    were all created NOT NULL with `server_default('0')`, so omitting them
    from an INSERT is harmless — Postgres fills in 0 itself. `price` and
    `is_active`, however, were created NOT NULL with NO server_default at
    all. Since the new, live Item model never references either column,
    every INSERT through it omits both, and Postgres rejects the row.
    `price` sorts first in the table's physical column order, so it is the
    one that surfaces in the error — but `is_active` has the exact same
    defect and would 500 immediately after price is fixed, on the next
    insert attempt.

Fix: bring `price` and `is_active` in line with their sibling legacy
columns (`cost`/`quantity_on_hand`/`reorder_level`) — keep NOT NULL (so the
`ck_items_non_negative` check constraint and general schema intent keep
meaning "every item has a real price/quantity", not silently-nullable), but
give both a server_default so an INSERT that (correctly, per the new
Item model) never mentions them still succeeds:
  - price      -> DEFAULT 0      (matches cost/quantity_on_hand/reorder_level)
  - is_active  -> DEFAULT true   (matches the retired plugin's own
                                   Python-side `Field(default=True)`, i.e.
                                   items were always meant to start active)

No application code changes needed — this is purely a DB-side gap between
an already-completed model cutover and a migration chain that never
followed it. Defensive/idempotent throughout, same helper pattern as every
other backfill migration in this chain (e.g. o5j0k1l2m3n4) — safe to
re-run, safe for a tenant that already has these defaults via some other
path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "p6k1l2m3n4o5"
down_revision: Union[str, None] = "o5j0k1l2m3n4"
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


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _table_exists(conn, schema, "items"):
        # Fresh/never-provisioned tenant schema — nothing to backfill; the
        # table will be created (by the original init migration) with
        # whatever DDL is current at provisioning time.
        return

    # `price` — legacy NOT NULL column with no default, orphaned by the
    # cutover to app/modules/inventory.Item (which never sets it). Give it
    # the same DEFAULT 0 its siblings (cost/quantity_on_hand/reorder_level)
    # have always had, so INSERTs that omit it (as every current caller
    # does) succeed instead of raising NotNullViolationError.
    if _column_exists(conn, schema, "items", "price") and _column_default(conn, schema, "items", "price") is None:
        op.alter_column(
            "items",
            "price",
            server_default=sa.text("0"),
            schema="tenant",
        )

    # `is_active` — same defect, same fix. Defaults to true (matches the
    # retired plugin's own Python-side `Field(default=True)`).
    if _column_exists(conn, schema, "items", "is_active") and _column_default(conn, schema, "items", "is_active") is None:
        op.alter_column(
            "items",
            "is_active",
            server_default=sa.text("true"),
            schema="tenant",
        )


def downgrade() -> None:
    # Not reversible — see o5j0k1l2m3n4/n4i9j0k1l2m3/f4a5b6c7d8e9 for the
    # same rationale: these defaults should have existed since the table
    # was first created (they exactly mirror cost/quantity_on_hand/
    # reorder_level, which have always had them); removing them would just
    # reintroduce the live bug this migration fixes.
    pass
