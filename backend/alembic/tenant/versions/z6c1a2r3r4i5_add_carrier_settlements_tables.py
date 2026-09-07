"""add_carrier_settlements_tables

Revision ID: z6c1a2r3r4i5
Revises: b7w2x3y4z5a6
Create Date: 2026-09-07 00:00:00.000000+00:00

DOWN_REVISION CORRECTION: originally authored against y5t0u1v2w3x4 (the
newest-by-mtime file at a glance), but that is NOT actually the chain tip —
a6v1w2x3y4z5 and b7w2x3y4z5a6 were added after it and are y5t0u1v2w3x4's
only descendants. Corrected to chain off the real tip, b7w2x3y4z5a6,
before this migration was ever applied anywhere (verified by rebuilding
the full revision graph from every file in this directory).

Also discovered while doing that graph rebuild: this repo already has a
second, pre-existing, unrelated dangling head — b2c3d4e5f6a1_add_sales_returns.py
(revision b2c3d4e5f6a1), branched off a1b2c3d4e5f6_add_sales_invoicing.py,
which itself is NOT an ancestor of the real chain at all (two disconnected
migration trees). b2c3d4e5f6a1 was left exactly as-is — NOT merged in
here. Its `op.create_table()` calls have no idempotent guards, and
Sales Returns already works live against every provisioned tenant in this
session (proven via `POST /sales/returns/{id}/credit-note` earlier this
same Wave 3 pass), which means the `sales_returns`/`sales_return_lines`
tables that migration would try to create already exist for every real
tenant — created by some other path (almost certainly
ddecea2865fa_create_missing_tables_and_columns.py, which IS in the real
chain). Actually running b2c3d4e5f6a1 against a provisioned tenant would
therefore fail with "relation already exists" and is never safe to do
blindly. Because of this pre-existing second head, plain `alembic ...
upgrade head` (what scripts/upgrade_tenants.py calls) is ambiguous and
will keep failing regardless of this migration — that is a separate,
pre-existing bug outside Wave 3 item 3's scope, left untouched here.
This migration must be applied by targeting this specific revision id
(`upgrade z6c1a2r3r4i5`), not bare `head`/`heads`.

WHY THIS EXISTS:
Live-confirmed bug while testing Wave 3 item 3 (Carrier COD Settlements):
`GET /api/v1/finance/settlements` 500s with
`asyncpg.exceptions.UndefinedTableError: relation "finance_carrier_settlements"
does not exist`.

Root cause: app/modules/finance/models/settlements.py defines
CarrierSettlement / SettlementLine / CarrierReceivableSnapshot (tables
finance_carrier_settlements / finance_settlement_lines /
finance_carrier_receivable_snapshots), and a full API + matching/posting
service layer already exists and is wired into the router — but no
migration in this chain ever created these tables. Unlike most models in
this codebase, these three do NOT inherit TenantBase and are NOT imported
by alembic/tenant/env.py's model-import block, so Alembic autogenerate
never had a chance to pick them up either. This feature has evidently
never been exercised end-to-end before now.

Enum columns (CarrierSettlement.state, SettlementLine.match_state,
SettlementLine.exception_type) needed a matching model fix alongside this
migration: their member NAMES are uppercase but VALUES are lowercase
(e.g. IMPORTED = "imported"), the same shape as
app.modules.finance.models.cheques.ChequeType/ChequeStatus — which
required `values_callable` to bind `.value` instead of SQLAlchemy's
default `.name` binding, plus explicit `schema="tenant"` +
`create_type=False` on the column (bare/unqualified enum casts do not
reliably resolve via the connection's search_path — see
ShiftStatus/EmployeeStatus in this same codebase for the identical
failure mode). Both fixes were applied together in
app/modules/finance/models/settlements.py so the model and this migration
agree on enum type names/values from the start; there was no prior
"passing" state for this feature to regress.

UPDATE (post-live-test): the model was originally authored with NO schema
declared on the SQLModel classes at all, on the assumption that
app/core/db/database.py's tenant_session() sets `SET search_path TO
tenant_<id>, public` per request. Live-tested against a real tenant after
this migration applied cleanly and the table was confirmed to physically
exist (via information_schema) — `GET /finance/settlements` still 500'd
with `relation "finance_carrier_settlements" does not exist`, and it
persisted across a full backend restart (ruling out stale connection-pool
state). Reading tenant_session()'s own docstring settled it:
`schema_translate_map={"tenant": schema}` is the ONLY routing mechanism —
there is no `SET search_path` at all, and the connection's real default
search_path is just `"$user", public` (confirmed live). So models with no
schema declared were never resolvable at runtime. Fixed by adding
`__table_args__ = {"schema": "tenant"}` to all three SQLModel classes in
app/modules/finance/models/settlements.py, and schema-qualifying
SettlementLine's `foreign_key="tenant.finance_carrier_settlements.id"` to
match (an unqualified FK string would fail mapper configuration once its
target table is schema-qualified). This migration's own DDL was already
correct — it always created the physical tables inside the real tenant
schema (via the `schema="tenant"` argument here, rewritten to the real
schema name by
alembic/tenant/env.py's before_cursor_execute token-rewrite listener) —
only the *type* casts needed the extra explicit schema qualification, not
table resolution, matching how sales_payments/pos_sales/etc. were already
created in past migrations without any schema on their SQLModel classes.

Defensive/idempotent via the same `_table_exists`/`_type_exists`
(information_schema/pg_type) guards used throughout this chain — safe to
re-run, safe for a tenant that already has some of this from a partial
prior attempt.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "z6c1a2r3r4i5"
down_revision: Union[str, None] = "b7w2x3y4z5a6"
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


def _type_exists(conn, schema: str, type_name: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND t.typname = :type_name"
        ),
        {"schema": schema, "type_name": type_name},
    ).scalar())


# Exact member VALUES of the corresponding StrEnum classes in
# app/modules/finance/models/settlements.py.
_CARRIER_SETTLEMENT_STATE_VALUES = (
    "imported", "matched", "partially_matched", "posted", "disputed",
)
_SETTLEMENT_LINE_MATCH_STATE_VALUES = (
    "matched", "fuzzy_matched", "unmatched", "disputed",
)
_SETTLEMENT_LINE_EXCEPTION_TYPE_VALUES = (
    "none", "remitted_but_not_delivered", "amount_mismatch",
    "unknown_awb", "duplicate_settlement",
)


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Native enum types (idempotent) ───────────────────────────────────
    if not _type_exists(conn, schema, "carriersettlementstate"):
        values_sql = ", ".join(f"'{v}'" for v in _CARRIER_SETTLEMENT_STATE_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."carriersettlementstate" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    if not _type_exists(conn, schema, "settlementlinematchstate"):
        values_sql = ", ".join(f"'{v}'" for v in _SETTLEMENT_LINE_MATCH_STATE_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."settlementlinematchstate" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    if not _type_exists(conn, schema, "settlementlineexceptiontype"):
        values_sql = ", ".join(f"'{v}'" for v in _SETTLEMENT_LINE_EXCEPTION_TYPE_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."settlementlineexceptiontype" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # IMPORTANT: must be postgresql.ENUM (dialect-specific) with
    # create_type=False — op.create_table()'s generic sa.Enum event handling
    # does not reliably honor create_type=False, and would emit a second,
    # colliding bare CREATE TYPE (see c7d8e9f0a1b2_add_cheques_table.py for
    # the same fix, same rationale).
    carrier_settlement_state_enum = postgresql.ENUM(
        *_CARRIER_SETTLEMENT_STATE_VALUES,
        name="carriersettlementstate",
        schema="tenant",
        create_type=False,
    )
    settlement_line_match_state_enum = postgresql.ENUM(
        *_SETTLEMENT_LINE_MATCH_STATE_VALUES,
        name="settlementlinematchstate",
        schema="tenant",
        create_type=False,
    )
    settlement_line_exception_type_enum = postgresql.ENUM(
        *_SETTLEMENT_LINE_EXCEPTION_TYPE_VALUES,
        name="settlementlineexceptiontype",
        schema="tenant",
        create_type=False,
    )

    # ── 2. finance_carrier_settlements ──────────────────────────────────────
    if not _table_exists(conn, schema, "finance_carrier_settlements"):
        op.create_table(
            "finance_carrier_settlements",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("carrier_code", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
            sa.Column("settlement_ref", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("gross_amount", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("total_fees", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("net_amount", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("state", carrier_settlement_state_enum, server_default="imported", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_carrier_settlements_carrier_code"),
            "finance_carrier_settlements", ["carrier_code"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_carrier_settlements_settlement_ref"),
            "finance_carrier_settlements", ["settlement_ref"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_carrier_settlements_state"),
            "finance_carrier_settlements", ["state"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_carrier_settlements_journal_entry_id"),
            "finance_carrier_settlements", ["journal_entry_id"], unique=False, schema="tenant",
        )

    # ── 3. finance_settlement_lines ─────────────────────────────────────────
    if not _table_exists(conn, schema, "finance_settlement_lines"):
        op.create_table(
            "finance_settlement_lines",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("settlement_id", sa.Uuid(), nullable=False),
            sa.Column("shipment_id", sa.Uuid(), nullable=True),
            sa.Column("awb_number", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("cod_collected", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("shipping_fee", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("cod_fee", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("return_fee", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("net_remitted", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("match_state", settlement_line_match_state_enum, server_default="unmatched", nullable=False),
            sa.Column("exception_type", settlement_line_exception_type_enum, server_default="none", nullable=False),
            sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(length=500), server_default="", nullable=False),
            # NOTE: constraint name kept under Postgres's 63-char identifier
            # limit — the natural "fk_finance_settlement_lines_settlement_id_
            # finance_carrier_settlements" name (matching the convention used
            # for pos_sales' FKs) is 72 chars and fails validate_identifier().
            sa.ForeignKeyConstraint(
                ["settlement_id"], ["tenant.finance_carrier_settlements.id"],
                name="fk_settlement_lines_settlement_id_carrier_settlements",
            ),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_settlement_lines_settlement_id"),
            "finance_settlement_lines", ["settlement_id"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_settlement_lines_shipment_id"),
            "finance_settlement_lines", ["shipment_id"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_settlement_lines_awb_number"),
            "finance_settlement_lines", ["awb_number"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_settlement_lines_match_state"),
            "finance_settlement_lines", ["match_state"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_settlement_lines_exception_type"),
            "finance_settlement_lines", ["exception_type"], unique=False, schema="tenant",
        )

    # ── 4. finance_carrier_receivable_snapshots ─────────────────────────────
    if not _table_exists(conn, schema, "finance_carrier_receivable_snapshots"):
        op.create_table(
            "finance_carrier_receivable_snapshots",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("carrier_code", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
            sa.Column("snapshot_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
            sa.Column("total_outstanding_cod", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("unsettled_shipments_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("aging_0_7_days", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("aging_8_14_days", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("aging_15_30_days", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.Column("aging_30_plus_days", sa.Numeric(precision=15, scale=4), server_default="0.0000", nullable=False),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_carrier_receivable_snapshots_carrier_code"),
            "finance_carrier_receivable_snapshots", ["carrier_code"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_finance_carrier_receivable_snapshots_snapshot_date"),
            "finance_carrier_receivable_snapshots", ["snapshot_date"], unique=False, schema="tenant",
        )


def downgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if _table_exists(conn, schema, "finance_carrier_receivable_snapshots"):
        op.drop_index(
            op.f("ix_tenant_finance_carrier_receivable_snapshots_snapshot_date"),
            table_name="finance_carrier_receivable_snapshots", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_carrier_receivable_snapshots_carrier_code"),
            table_name="finance_carrier_receivable_snapshots", schema="tenant",
        )
        op.drop_table("finance_carrier_receivable_snapshots", schema="tenant")

    if _table_exists(conn, schema, "finance_settlement_lines"):
        op.drop_index(
            op.f("ix_tenant_finance_settlement_lines_exception_type"),
            table_name="finance_settlement_lines", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_settlement_lines_match_state"),
            table_name="finance_settlement_lines", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_settlement_lines_awb_number"),
            table_name="finance_settlement_lines", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_settlement_lines_shipment_id"),
            table_name="finance_settlement_lines", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_settlement_lines_settlement_id"),
            table_name="finance_settlement_lines", schema="tenant",
        )
        op.drop_table("finance_settlement_lines", schema="tenant")

    if _table_exists(conn, schema, "finance_carrier_settlements"):
        op.drop_index(
            op.f("ix_tenant_finance_carrier_settlements_journal_entry_id"),
            table_name="finance_carrier_settlements", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_carrier_settlements_state"),
            table_name="finance_carrier_settlements", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_carrier_settlements_settlement_ref"),
            table_name="finance_carrier_settlements", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_finance_carrier_settlements_carrier_code"),
            table_name="finance_carrier_settlements", schema="tenant",
        )
        op.drop_table("finance_carrier_settlements", schema="tenant")

    op.execute('DROP TYPE IF EXISTS "tenant"."settlementlineexceptiontype"')
    op.execute('DROP TYPE IF EXISTS "tenant"."settlementlinematchstate"')
    op.execute('DROP TYPE IF EXISTS "tenant"."carriersettlementstate"')
