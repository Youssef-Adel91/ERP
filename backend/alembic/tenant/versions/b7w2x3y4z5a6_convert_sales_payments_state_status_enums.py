"""convert_sales_payments_state_status_enums

Revision ID: b7w2x3y4z5a6
Revises: a6v1w2x3y4z5
Create Date: 2026-09-04 00:00:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed bug: `POST /api/v1/sales/payments` 500s for every request
with:

    asyncpg.exceptions.UndefinedObjectError: type "salespaymentstatus"
    does not exist
    [SQL: INSERT INTO tenant_....sales_payments (..., status) VALUES
    (..., $21::salespaymentstatus)]

Same bug class as q7l2m3n4o5p6_create_purchaseorderstatus_type.py and
s9n4o5p6q7r8_convert_purchasing_state_status_enums.py:
y5t0u1v2w3x4_add_sales_payments.py's CREATE TABLE was written by copying
h8c3d4e5f6g7_phase_4b_step4_payments.py's `supplier_payments` shape, which
declares both `state` and `status` as plain `varchar` columns even though
the ORM models declare them as native Postgres ENUM columns:

  - `state` (from `DocumentLifecycleMixin`) is
    `sa.Enum(DocumentState, name="documentstate", schema="tenant",
    create_type=False)`. The `documentstate` type already exists (created
    by d4e5f6a1b2c3_phase_4a_approvals.py and used correctly by other
    DocumentLifecycleMixin tables) — only the `sales_payments.state`
    column itself was left as `varchar(20)` by y5t0u1v2w3x4 and needs
    converting, no new type needed.
  - `status` (`SalesPayment.status`, app/modules/sales/models/payments.py)
    is now declared `sa.Enum(SalesPaymentStatus, name="salespaymentstatus",
    schema="tenant")` (this migration's companion model fix — it was
    previously a bare, unqualified `sa.Enum(SalesPaymentStatus)`) but no
    migration ever creates a `salespaymentstatus` type, and
    y5t0u1v2w3x4 created the column as plain `varchar(20)`.
    `SalesPaymentStatus` members (app/modules/sales/models/payments.py):
    DRAFT, POSTED, CANCELLED.

Since y5t0u1v2w3x4 and a6v1w2x3y4z5 have already been applied (per this
project's rule, an already-applied migration file is never edited), this
is a new, additive migration. No `sales_payments` rows exist yet in any
tenant (this table was only just created and the first insert attempt is
what surfaced this bug), so the `USING` casts below are safe regardless.

Defensive/idempotent throughout, exact same helper pattern as
q7l2m3n4o5p6/s9n4o5p6q7r8 (`_type_exists`, `_column_udt_name`) — safe to
re-run, safe for a tenant that already has the type and/or the column
conversions via some other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7w2x3y4z5a6"
down_revision: Union[str, None] = "a6v1w2x3y4z5"
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


# Exact member values of app.modules.sales.models.payments.SalesPaymentStatus.
_SALES_PAYMENT_STATUS_VALUES = (
    "DRAFT",
    "POSTED",
    "CANCELLED",
)


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. documentstate already exists (d4e5f6a1b2c3) — just convert the
    #        column y5t0u1v2w3x4 left as varchar(20). ──────────────────────
    _convert_column_to_enum(
        conn, schema, "sales_payments", "state", "documentstate", "DRAFT",
    )

    # ── 2. Create the missing salespaymentstatus enum type ─────────────────
    if not _type_exists(conn, schema, "salespaymentstatus"):
        values_sql = ", ".join(f"'{v}'" for v in _SALES_PAYMENT_STATUS_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."salespaymentstatus" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── 3. Convert sales_payments.status from its original varchar(20)
    #        (y5t0u1v2w3x4_add_sales_payments.py) to the enum type the
    #        model actually expects. No-op if already converted. ───────────
    _convert_column_to_enum(
        conn, schema, "sales_payments", "status", "salespaymentstatus", "DRAFT",
    )


def downgrade() -> None:
    # Not reversible — same rationale as every other enum-conversion
    # backfill in this chain: these types and column conversions should
    # have existed since sales_payments was first created; reverting
    # either would just reintroduce the live 500.
    pass
