"""backfill_lifecycle_cols_and_carriers

Revision ID: n4i9j0k1l2m3
Revises: m3h8i9j0k1l2
Create Date: 2026-08-22 00:00:00.000000+00:00

WHY THIS EXISTS:
Two independent bugs found via live testing against the running app (not
just code review):

1. `DocumentLifecycleMixin` columns (`posted_at`, `reversal_of_id`) are
   missing on three tables whose CREATE TABLE migration predates the
   mixin gaining those two fields:
     - purchase_orders  (e5f6a1b2c3d4_phase_4b_purchasing.py)
     - goods_receipts   (e5f6a1b2c3d4_phase_4b_purchasing.py)
     - import_shipments (g7b2c3d4e5f6_phase_4b_step3_landed_cost.py)
   Confirmed LIVE: `GET /api/v1/purchasing/orders` -> 500
   `asyncpg.exceptions.UndefinedColumnError: column purchase_orders.posted_at
   does not exist`.
   goods_receipts/import_shipments are not yet live-confirmed but were
   verified missing both columns by direct inspection of their CREATE
   TABLE migrations (no later migration in the chain ever adds them —
   confirmed via full-chain grep), so they are fixed proactively here
   rather than waiting for the next round-trip (same rationale as
   f4a5b6c7d8e9's supplier_payments fix).

   NOTE — corrections to an earlier (uncofirmed, static-analysis-only)
   candidate list: `journal_entries`, `sales_invoices`, and `sales_returns`
   were also flagged as candidates, but are NOT touched by this migration
   because they are proven, by reading d4e5f6a1b2c3_phase_4a_approvals.py
   (which explicitly loops over exactly those three tables and adds
   state/content_hash/submitted_at/submitted_by/approved_at/posted_at/
   reversal_of_id, skipping posted_at only for journal_entries because it
   already had that column from 226439fee167_init_tenant.py), to already
   have every DocumentLifecycleMixin column. This matches the live test
   result of `GET /api/v1/sales/invoices` returning a clean `200 []`.

   This migration is idempotent (table/column-existence guarded) using the
   exact same helper pattern as f4a5b6c7d8e9_backfill_document_lifecycle_columns.py,
   just with an extended table list — safe to re-run, safe for tenants
   that already have these columns via some other path.

2. `carrier_account`, `shipment`, `shipment_event`, `carrier_webhook_event`
   tables do not exist anywhere in the tenant migration chain at all
   (confirmed via full grep of this directory for "carrier" — zero
   matches before this file), even though
   app/modules/logistics/models/carriers.py defines all four as ORM
   tables. Confirmed LIVE: every request to
   `GET/POST /api/v1/webhooks/carriers/{bosta,mylerz}` -> 500
   `asyncpg.exceptions.UndefinedTableError`.

   IMPORTANT MODEL BUG FOUND & FIXED ALONGSIDE THIS MIGRATION: none of the
   four classes in carriers.py declared an explicit `__tablename__` (every
   other multi-word model in this codebase does — e.g. ItemVariant ->
   "item_variants", StockLevel -> "stock_levels" — specifically to avoid
   this exact pitfall). Without one, SQLModel's default table-naming falls
   back to `cls.__name__.lower()` with NO underscore insertion (verified
   empirically against the installed sqlmodel package: CarrierAccount ->
   "carrieraccount", ShipmentEvent -> "shipmentevent", NOT "carrier_account"
   / "shipment_event"). Creating tables literally named "carrier_account"
   etc. without also fixing the model would NOT have fixed the live 500s —
   SQLAlchemy would still compile queries against "carrieraccount". Fixed
   by adding explicit __tablename__ to all four classes in carriers.py
   (separate, non-migration code change, committed alongside this file) so
   the runtime table names now match what this migration creates.

   Table creation follows the models in carriers.py column-for-column:
   ShipmentState is stored as a plain VARCHAR column (not a Postgres ENUM
   type) in both Shipment.state and ShipmentEvent.canonical_state — the
   model explicitly overrides with `sa_column=Column(String, ...)` for the
   same reason app/modules/inventory/models/core.py's Item.costing_method
   does (documented there): avoiding a native Postgres ENUM type that no
   migration would otherwise create. So this migration creates no new
   Postgres ENUM types at all.

Defensive/idempotent throughout: every op.create_table/add_column/
create_index call is guarded by an information_schema existence check, so
this migration is safe to re-run and safe for a tenant schema that
already has some of these objects via a different path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "n4i9j0k1l2m3"
down_revision: Union[str, None] = "m3h8i9j0k1l2"
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

    # ── 1. Backfill DocumentLifecycleMixin columns ─────────────────────────
    for table in ("purchase_orders", "goods_receipts", "import_shipments"):
        _backfill_document_lifecycle_columns(conn, schema, table)

    # ── 2. Create carrier/shipment tables (FR-750/753/756/760/752) ────────

    if not _table_exists(conn, schema, "carrier_account"):
        op.create_table(
            "carrier_account",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("carrier_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("credentials_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("webhook_secret_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.UniqueConstraint("carrier_code", name="uq_carrier_account_code"),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_carrier_account_carrier_code"),
            "carrier_account", ["carrier_code"], unique=False, schema="tenant",
        )

    if not _table_exists(conn, schema, "shipment"):
        op.create_table(
            "shipment",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invoice_id", sa.Uuid(), nullable=False),
            sa.Column("carrier_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("awb_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("tracking_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("state", sqlmodel.sql.sqltypes.AutoString(), server_default="created", nullable=False),
            sa.Column("cod_amount", sa.Numeric(precision=18, scale=4), server_default="0.0000", nullable=False),
            sa.Column("return_received_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("carrier_code", "awb_number", name="uq_shipment_carrier_awb"),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index("ix_shipment_invoice_id", "shipment", ["invoice_id"], unique=False, schema="tenant")
        op.create_index("ix_shipment_awb", "shipment", ["awb_number"], unique=False, schema="tenant")

    if not _table_exists(conn, schema, "shipment_event"):
        op.create_table(
            "shipment_event",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("shipment_id", sa.Uuid(), nullable=False),
            sa.Column("carrier_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("carrier_status_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("canonical_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index("ix_shipment_event_shipment_id", "shipment_event", ["shipment_id"], unique=False, schema="tenant")

    if not _table_exists(conn, schema, "carrier_webhook_event"):
        op.create_table(
            "carrier_webhook_event",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("carrier_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("dedupe_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("headers_json", sa.JSON(), nullable=False),
            sa.Column("signature_valid", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("dedupe_key", name="uq_carrier_webhook_event_dedupe_key"),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            "ix_carrier_webhook_dedupe", "carrier_webhook_event", ["dedupe_key"], unique=False, schema="tenant",
        )


def downgrade() -> None:
    # Not reversible for the DocumentLifecycleMixin backfill portion — same
    # rationale as f4a5b6c7d8e9 (these columns should have existed since
    # the tables were first created; removing them would just reintroduce
    # the bug).
    #
    # The new carrier/shipment tables ARE reversible since they are wholly
    # new in this migration.
    conn = op.get_bind()
    schema = _get_schema()

    if _table_exists(conn, schema, "carrier_webhook_event"):
        op.drop_index("ix_carrier_webhook_dedupe", table_name="carrier_webhook_event", schema="tenant")
        op.drop_table("carrier_webhook_event", schema="tenant")

    if _table_exists(conn, schema, "shipment_event"):
        op.drop_index("ix_shipment_event_shipment_id", table_name="shipment_event", schema="tenant")
        op.drop_table("shipment_event", schema="tenant")

    if _table_exists(conn, schema, "shipment"):
        op.drop_index("ix_shipment_awb", table_name="shipment", schema="tenant")
        op.drop_index("ix_shipment_invoice_id", table_name="shipment", schema="tenant")
        op.drop_table("shipment", schema="tenant")

    if _table_exists(conn, schema, "carrier_account"):
        op.drop_index(op.f("ix_tenant_carrier_account_carrier_code"), table_name="carrier_account", schema="tenant")
        op.drop_table("carrier_account", schema="tenant")
