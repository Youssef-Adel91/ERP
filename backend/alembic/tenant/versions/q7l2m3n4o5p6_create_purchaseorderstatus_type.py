"""create_purchaseorderstatus_type

Revision ID: q7l2m3n4o5p6
Revises: p6k1l2m3n4o5
Create Date: 2026-08-22 20:00:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed bug: `POST /api/v1/purchasing/orders` 500s for every request
with:

    asyncpg.exceptions.UndefinedObjectError: type
    "tenant_<id>.purchaseorderstatus" does not exist
    [SQL: INSERT INTO tenant_....purchase_orders (..., status) VALUES
    (..., $21::tenant_<id>.purchaseorderstatus)]

Root cause, confirmed by reading `app/modules/purchasing/models/core.py`
and every migration that has ever touched `tenant.purchase_orders`:

  - `PurchaseOrder.status` is declared as
    `sa.Enum(PurchaseOrderStatus, name="purchaseorderstatus", schema="tenant")`
    — the cast in the failing INSERT is correctly schema-qualified, so the
    ORM-side declaration itself is fine.
  - The `purchase_orders` table was created by
    e5f6a1b2c3d4_phase_4b_purchasing.py. That migration's `status` column
    is `sa.Column("status", sa.String(length=50), nullable=False,
    server_default="DRAFT")` — a plain VARCHAR, NOT an enum column. No
    `CREATE TYPE` for `purchaseorderstatus` (or any other name for this
    same concept — searched for `purchase_order_status`, `pordertype`,
    etc., no matches) appears anywhere in
    backend/alembic/tenant/versions/. This is not a naming-drift bug (no
    type was ever created under a different name for this column) — the
    type has simply never existed in any tenant schema, on any migration
    path, since the table was first created.
  - Every later migration that touches `purchase_orders`
    (n4i9j0k1l2m3, o5j0k1l2m3n4) only adds/backfills unrelated columns
    (posted_at, reversal_of_id, created_by, updated_by, deleted_at) and
    never revisits `status`.

Because the type has never existed, the model's `sa.Enum(...)` column
definition has been broken for every tenant since e5f6a1b2c3d4 first
shipped — this migration creates the missing type AND converts the
already-live `status` column (currently `varchar(50)`, per
e5f6a1b2c3d4) to actually use it, matching the model. Converting the
column type is necessary too: even after the type exists, SQLAlchemy will
keep emitting `$N::tenant.purchaseorderstatus` casts (per the mapped
column's declared type), and assigning that enum value into a
still-`varchar` column fails with a *different* error ("column status is
of type character varying but expression is of type
tenant.purchaseorderstatus"). Wave-1 testing indicates purchase-order
creation has been broken/untested until now, so no tenant has any
`purchase_orders` rows at risk from the `USING` cast.

Defensive/idempotent throughout, same helper pattern as
o5j0k1l2m3n4_backfill_purchasing_audit_cols_and_pos.py (`_type_exists`)
— safe to re-run, safe for a tenant that already has the type and/or the
column already converted via some other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "q7l2m3n4o5p6"
down_revision: Union[str, None] = "p6k1l2m3n4o5"
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


def _type_exists(conn, schema: str, type_name: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND t.typname = :type_name"
        ),
        {"schema": schema, "type_name": type_name},
    ).scalar())


def _column_udt_name(conn, schema: str, table: str, column: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()


# Exact member values of app.modules.purchasing.models.core.PurchaseOrderStatus.
_PURCHASE_ORDER_STATUS_VALUES = (
    "DRAFT",
    "CONFIRMED",
    "PARTIALLY_RECEIVED",
    "RECEIVED",
    "BILLED",
    "CANCELLED",
    "CLOSED",
)


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Create the missing enum type ─────────────────────────────────────
    if not _type_exists(conn, schema, "purchaseorderstatus"):
        values_sql = ", ".join(f"'{v}'" for v in _PURCHASE_ORDER_STATUS_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."purchaseorderstatus" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── 2. Convert purchase_orders.status from its original varchar(50)
    #        (e5f6a1b2c3d4_phase_4b_purchasing.py) to the enum type the
    #        model actually expects. No-op if already converted. ───────────
    udt_name = _column_udt_name(conn, schema, "purchase_orders", "status")
    if udt_name is not None and udt_name != "purchaseorderstatus":
        op.execute(
            'ALTER TABLE "tenant"."purchase_orders" '
            'ALTER COLUMN status DROP DEFAULT, '
            'ALTER COLUMN status TYPE "tenant"."purchaseorderstatus" '
            'USING status::text::"tenant"."purchaseorderstatus", '
            "ALTER COLUMN status SET DEFAULT 'DRAFT'::\"tenant\".\"purchaseorderstatus\""
        )


def downgrade() -> None:
    # Not reversible — see f4a5b6c7d8e9/e8f9a0b1c2d3/n4i9j0k1l2m3/
    # o5j0k1l2m3n4 for the same rationale: this type and column conversion
    # should have existed since purchase_orders was first created;
    # reverting either would just reintroduce the live 500.
    pass
