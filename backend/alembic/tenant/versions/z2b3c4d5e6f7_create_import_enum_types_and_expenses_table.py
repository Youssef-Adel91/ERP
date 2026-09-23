"""create_import_enum_types_and_expenses_table

Revision ID: z2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-09-23 00:05:00.000000+00:00

WHY THIS EXISTS:
Live-reproduced: `GET /api/v1/imports/dossiers` 500s for every tenant.
Same bug class as z1a2b3c4d5e6 (payslipstatus): `ImportDossier.status` and
`ImportExpense.expense_type` were bare Enum fields with no explicit
`sa_column=Column(sa.Enum(..., schema="tenant", create_type=False))`.
Fixed in app/modules/imports/models/core.py; this migration backfills
already-provisioned tenant schemas the same way z1a2b3c4d5e6 does for
hr_payslips: create the enum type if missing, create the table if it
somehow doesn't exist (older/alembic-only tenants), otherwise convert the
existing column to the correctly-qualified type.

Also creates `import_dossier_cost_layers` (DossierCostLayer model) if
missing -- it was never in any migration NOR in provision_tenant_schema's
create_all table list until this session's fix added it there; no live
500 has been reproduced against it (no UI path currently exercises it),
but it is cheap and safe to backfill alongside its sibling tables here
rather than leaving a silent gap for whenever that feature is wired up.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "z2b3c4d5e6f7"
down_revision: Union[str, None] = "z1a2b3c4d5e6"
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


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    ).scalar())


def _column_udt_name(conn, schema: str, table: str, column: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()


_IMPORT_STATUS_VALUES = ("OPEN", "CUSTOMS", "CLEARED", "CLOSED")
_EXPENSE_TYPE_VALUES = ("FREIGHT", "CUSTOMS", "CLEARANCE", "OTHER")


def _ensure_enum(op, conn, schema: str, type_name: str, values: tuple[str, ...]) -> None:
    if not _type_exists(conn, schema, type_name):
        values_sql = ", ".join(f"'{v}'" for v in values)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."{type_name}" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)


def _convert_column_if_needed(op, conn, schema: str, table: str, column: str, type_name: str) -> None:
    udt_name = _column_udt_name(conn, schema, table, column)
    if udt_name is not None and udt_name != type_name:
        op.execute(
            f'ALTER TABLE "tenant"."{table}" '
            f'ALTER COLUMN {column} TYPE "tenant"."{type_name}" '
            f'USING {column}::text::"tenant"."{type_name}"'
        )


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    _ensure_enum(op, conn, schema, "importstatus", _IMPORT_STATUS_VALUES)
    _ensure_enum(op, conn, schema, "expensetype", _EXPENSE_TYPE_VALUES)

    # ── import_dossiers ─────────────────────────────────────────────────
    if not _table_exists(conn, schema, "import_dossiers"):
        op.create_table(
            "import_dossiers",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dossier_number", sa.String(length=100), nullable=False),
            sa.Column("supplier_id", sa.Uuid(), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(*_IMPORT_STATUS_VALUES, name="importstatus", schema="tenant", create_type=False),
                nullable=False,
            ),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dossier_number"),
            schema="tenant",
        )
        op.create_index(op.f("ix_tenant_import_dossiers_supplier_id"), "import_dossiers", ["supplier_id"], schema="tenant")
    else:
        _convert_column_if_needed(op, conn, schema, "import_dossiers", "status", "importstatus")

    # ── import_expenses ─────────────────────────────────────────────────
    if not _table_exists(conn, schema, "import_expenses"):
        op.create_table(
            "import_expenses",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dossier_id", sa.Uuid(), nullable=False),
            sa.Column(
                "expense_type",
                postgresql.ENUM(*_EXPENSE_TYPE_VALUES, name="expensetype", schema="tenant", create_type=False),
                nullable=False,
            ),
            sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("vendor_id", sa.Uuid(), nullable=True),
            sa.ForeignKeyConstraint(["dossier_id"], ["tenant.import_dossiers.id"]),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(op.f("ix_tenant_import_expenses_dossier_id"), "import_expenses", ["dossier_id"], schema="tenant")
        op.create_index(op.f("ix_tenant_import_expenses_vendor_id"), "import_expenses", ["vendor_id"], schema="tenant")
    else:
        _convert_column_if_needed(op, conn, schema, "import_expenses", "expense_type", "expensetype")

    # ── import_dossier_cost_layers (no enum column -- create if missing) ──
    if not _table_exists(conn, schema, "import_dossier_cost_layers") and _table_exists(conn, schema, "cost_layers"):
        op.create_table(
            "import_dossier_cost_layers",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dossier_id", sa.Uuid(), nullable=False),
            sa.Column("layer_id", sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(["dossier_id"], ["tenant.import_dossiers.id"]),
            sa.ForeignKeyConstraint(["layer_id"], ["tenant.cost_layers.id"]),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(op.f("ix_tenant_import_dossier_cost_layers_dossier_id"), "import_dossier_cost_layers", ["dossier_id"], schema="tenant")
        op.create_index(op.f("ix_tenant_import_dossier_cost_layers_layer_id"), "import_dossier_cost_layers", ["layer_id"], schema="tenant")


def downgrade() -> None:
    # Not reversible -- same rationale as sibling migrations in this chain.
    pass
