"""convert_purchasing_state_status_enums

Revision ID: s9n4o5p6q7r8
Revises: r8m3n4o5p6q7
Create Date: 2026-08-22 22:30:00.000000+00:00

WHY THIS EXISTS:
Deliberate follow-up on the three items r8m3n4o5p6q7's docstring flagged
under "OTHER MISMATCHES FOUND BUT NOT FIXED HERE" and deferred for a human
decision. All three are the exact same bug class already fixed once in
this chain for `purchase_orders.status` -> `purchaseorderstatus`
(q7l2m3n4o5p6): a column that e5f6a1b2c3d4_phase_4b_purchasing.py created
as a plain `varchar(50)` where the ORM model declares a real Postgres
ENUM column, so any INSERT/UPDATE where SQLAlchemy emits its usual
`$N::tenant.<enum>` cast fails with "column ... is of type character
varying but expression is of type tenant.<enum>".

Re-verified directly against current model/migration source before writing
this migration (not just trusting the prior docstring):

  1. `purchase_orders.state` / `goods_receipts.state` — both models use
     `DocumentLifecycleMixin` (app/core/models/mixins.py), which declares
     `state` as `sa.Enum(DocumentState, name="documentstate",
     schema="tenant", create_type=False)`. The `documentstate` type DOES
     already exist (created by d4e5f6a1b2c3_phase_4a_approvals.py and used
     correctly by other DocumentLifecycleMixin tables created via
     ddecea2865fa) — only the `purchase_orders`/`goods_receipts` columns
     themselves were left as `varchar(50)` by e5f6a1b2c3d4 and never
     converted. `DocumentState` members (app/core/models/mixins.py):
     DRAFT, PENDING_APPROVAL, APPROVED, POSTED, REJECTED, CANCELLED,
     WITHDRAWN, REVERSED, CLOSED.

  2. `goods_receipts.status` — `GoodsReceipt.status`
     (app/modules/purchasing/models/core.py) is declared
     `sa.Enum(GoodsReceiptStatus, name="goodsreceiptstatus",
     schema="tenant")` (no `create_type=False`, same as
     `PurchaseOrderStatus` before q7l2m3n4o5p6 fixed it) but no migration
     anywhere in backend/alembic/tenant/versions/ ever creates a
     `goodsreceiptstatus` type (confirmed via full-directory search — zero
     matches) and e5f6a1b2c3d4 created the column as plain `varchar(50)`.
     `GoodsReceiptStatus` members (app/modules/purchasing/models/core.py):
     DRAFT, POSTED, CANCELLED.

Also re-verified the complete column lists of PurchaseOrder,
PurchaseOrderLine, GoodsReceipt, and GoodsReceiptLine against every
migration that has ever touched these four tables (e5f6a1b2c3d4,
n4i9j0k1l2m3, o5j0k1l2m3n4, q7l2m3n4o5p6, r8m3n4o5p6q7) looking for any
other enum-backed column with this same bug class. None of the *Line
tables declare any enum column at all (qty_*/unit_*/expected_* are all
Numeric, serial_ids is JSON). BaseMixin/TenantBase (app/core/db/base.py)
contributes no enum columns either. So `state` (both parent tables) and
`status` (both parent tables) are the only enum-typed columns on any of
the four tables — all three broken instances are fixed here; nothing else
of this class remains.

(Not touched, out of scope for this migration — not an enum-type bug:
purchase_orders/goods_receipts carry legacy `approved_by`, `rejected_at`,
`rejected_by`, `rejection_reason` columns from e5f6a1b2c3d4 that the
current DocumentLifecycleMixin no longer maps. They are harmless orphaned
columns, not a broken enum cast, and removing them is a separate decision
outside this fix's scope.)

Wave-1 testing today established PO/goods-receipt creation was broken
until r8m3n4o5p6q7 (created_at/updated_at server_default gap) was applied
moments before this file was written, so the test tenant's
purchase_orders/goods_receipts should be empty. Data state cannot be
verified across every tenant schema from here, so — same as
q7l2m3n4o5p6 — this migration is made idempotent and its `USING` casts
safe regardless: every value written to these columns has only ever come
from the Python enums above (DRAFT/POSTED/CANCELLED/etc., all uppercase,
no free text path exists), so `col::text::"tenant"."<enum>"` cannot fail
on any row actually produced by this application.

Defensive/idempotent throughout, exact same helper pattern as
q7l2m3n4o5p6_create_purchaseorderstatus_type.py (`_type_exists`,
`_column_udt_name`) — safe to re-run, safe for a tenant that already has
some/all of these types and/or column conversions via some other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "s9n4o5p6q7r8"
down_revision: Union[str, None] = "r8m3n4o5p6q7"
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


# Exact member values of app.core.models.mixins.DocumentState.
_DOCUMENT_STATE_VALUES = (
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "POSTED",
    "REJECTED",
    "CANCELLED",
    "WITHDRAWN",
    "REVERSED",
    "CLOSED",
)

# Exact member values of app.modules.purchasing.models.core.GoodsReceiptStatus.
_GOODS_RECEIPT_STATUS_VALUES = (
    "DRAFT",
    "POSTED",
    "CANCELLED",
)


def _convert_column_to_enum(
    conn,
    schema: str,
    table: str,
    column: str,
    type_name: str,
    default_value: str,
) -> None:
    udt_name = _column_udt_name(conn, schema, table, column)
    if udt_name is not None and udt_name != type_name:
        op.execute(
            f'ALTER TABLE "tenant"."{table}" '
            f"ALTER COLUMN {column} DROP DEFAULT, "
            f'ALTER COLUMN {column} TYPE "tenant"."{type_name}" '
            f'USING {column}::text::"tenant"."{type_name}", '
            f"ALTER COLUMN {column} SET DEFAULT '{default_value}'::\"tenant\".\"{type_name}\""
        )


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. documentstate already exists (d4e5f6a1b2c3) — just convert the
    #        two columns e5f6a1b2c3d4 left as varchar(50). ──────────────────
    for table in ("purchase_orders", "goods_receipts"):
        _convert_column_to_enum(
            conn, schema, table, "state", "documentstate", "DRAFT",
        )

    # ── 2. Create the missing goodsreceiptstatus enum type ─────────────────
    if not _type_exists(conn, schema, "goodsreceiptstatus"):
        values_sql = ", ".join(f"'{v}'" for v in _GOODS_RECEIPT_STATUS_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."goodsreceiptstatus" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── 3. Convert goods_receipts.status from its original varchar(50)
    #        (e5f6a1b2c3d4_phase_4b_purchasing.py) to the enum type the
    #        model actually expects. No-op if already converted. ───────────
    _convert_column_to_enum(
        conn, schema, "goods_receipts", "status", "goodsreceiptstatus", "DRAFT",
    )


def downgrade() -> None:
    # Not reversible — see q7l2m3n4o5p6/r8m3n4o5p6q7 and every other
    # backfill in this chain for the same rationale: these enum types and
    # column conversions should have existed since purchase_orders/
    # goods_receipts were first created; reverting either would just
    # reintroduce the live "column ... is of type character varying but
    # expression is of type tenant.<enum>" failure.
    pass
