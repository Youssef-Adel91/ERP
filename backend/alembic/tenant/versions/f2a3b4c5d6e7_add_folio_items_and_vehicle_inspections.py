"""add_folio_items_and_vehicle_inspections

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-15 00:00:00.000000+00:00

WHY THIS EXISTS (live-confirmed P0, 14 Sep 2026)
------------------------------------------------
Two plugin tables were defined as real SQLModel `table=True` models but no
Alembic revision had ever created them:

  * `folio_items`         — app/plugins/hospitality/models/folio.py (FolioItem)
  * `vehicle_inspections` — app/plugins/rental/models/inspection.py (VehicleInspection)

Confirmed by reading every one of the 49 revisions in alembic/tenant/versions/:
the strings "folio_items" and "vehicle_inspections" appear in exactly zero
`op.create_table(...)` calls (the only textual hit anywhere is an unrelated
prose comment in v2q7r8s9t0u1 mentioning "Hospitality folio").

Live symptom on tenant tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f:

    POST /api/v1/cases/{id}/transition  {"to_stage": "returned"}   → 500
    case.data["posting_error"] recorded by the rental listener itself:
      "ProgrammingError: <asyncpg.exceptions.UndefinedTableError>: relation
       \"tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f.vehicle_inspections\"
       does not exist"

    POST /api/v1/hospitality/reservations/{id}/folio/items          → 500
    GET  /api/v1/hospitality/reservations/{id}/folio                → 500
    POST /api/v1/cases/{id}/transition  {"to_stage": "checked_out"} → 500

The failing SELECT aborts the request's Postgres transaction, so the caller's
subsequent COMMIT fails too — which is why the whole checkout / vehicle-return
step 500s and the case stays stuck in `checked_in` / `picked_up` forever, and
why neither vertical could ever emit its SalesInvoice or journal entry.

Root cause of the gap: alembic/tenant/env.py imports the model packages so that
`TenantBase.metadata` is populated for autogenerate — but it never imported
app.plugins.hospitality.models.folio or app.plugins.rental.models.inspection, so
both tables were invisible to every `alembic revision --autogenerate` run ever
made. (That import gap is fixed in the same change as this revision.)

Note that app/core/db/database.py's create_all()-based provisioning fast path
DOES list FolioItem.__table__ / VehicleInspection.__table__, so a tenant
provisioned through that path gets the tables; this revision is what fixes every
tenant provisioned before those entries existed, and the
`alembic upgrade head` provisioning path used by
app/workers/tasks/main.py::reconcile_provisioning.

ENUM VALUES — names, not values
--------------------------------
SQLAlchemy's `sa.Enum(PyEnumClass, ...)` persists the *names* of the members,
not their `.value` strings. So the Postgres types below carry ROOM_CHARGE /
PICKUP / THREE_QUARTERS, matching what the ORM actually binds — even though
e.g. FuelLevel.THREE_QUARTERS's Python value is the string "3/4".

Idempotent throughout (`_type_exists` / `_table_exists` guards + the
`DO $$ ... EXCEPTION WHEN duplicate_object` pattern already used by
q7l2m3n4o5p6 and w3r8s9t0u1v2), so it is safe to re-run and safe for a tenant
that already received these tables via the create_all() path.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers (same pattern as w3r8s9t0u1v2 / q7l2m3n4o5p6) ──────────────────────


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
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :schema AND t.typname = :type_name"
            ),
            {"schema": schema, "type_name": type_name},
        ).scalar()
    )


def _table_exists(conn, schema: str, table: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


# Exact member NAMES of the Python enums these columns are typed with.
_FOLIO_ITEM_CATEGORY_VALUES = (
    "ROOM_CHARGE",
    "RESTAURANT",
    "LAUNDRY",
    "MINIBAR",
    "SPA",
    "TELEPHONE",
    "TRANSPORT",
    "TAX",
    "SERVICE_CHARGE",
    "DISCOUNT",
    "DEPOSIT",
    "OTHER",
)
_VEHICLE_INSPECTION_TYPE_VALUES = ("PICKUP", "RETURN")
_VEHICLE_FUEL_LEVEL_VALUES = ("EMPTY", "QUARTER", "HALF", "THREE_QUARTERS", "FULL")


def _column_udt(conn, schema: str, table: str, column: str) -> tuple[str | None, str | None]:
    """Return (udt_schema, udt_name) for a column, or (None, None) if absent."""
    row = conn.execute(
        sa.text(
            "SELECT udt_schema, udt_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).first()
    return (row[0], row[1]) if row else (None, None)


def _ensure_column_enum_in_schema(
    conn, schema: str, table: str, column: str, type_name: str
) -> None:
    """Re-point a column at the tenant-schema copy of its enum type.

    Covers tenants provisioned through app/core/db/database.py's create_all()
    fast path BEFORE the models declared `schema="tenant"` on these enums: back
    then SQLAlchemy emitted an unqualified `CREATE TYPE folio_item_category`,
    which landed in whatever the connection's search_path resolved to (public),
    shared across every tenant. Same corrective pattern as
    w3r8s9t0u1v2_create_employeestatus_type.py.
    """
    udt_schema, udt_name = _column_udt(conn, schema, table, column)
    if udt_name != type_name or udt_schema == schema:
        return
    op.execute(
        f'ALTER TABLE "tenant"."{table}" '
        f'ALTER COLUMN {column} TYPE "tenant"."{type_name}" '
        f'USING {column}::text::"tenant"."{type_name}"'
    )


def _create_enum(conn, schema: str, type_name: str, values: tuple[str, ...]) -> None:
    """Create a tenant-schema enum type if it isn't already there.

    The literal `"tenant".` token is rewritten to the real schema name by the
    before_cursor_execute listener installed in alembic/tenant/env.py.
    """
    if _type_exists(conn, schema, type_name):
        return
    values_sql = ", ".join(f"'{v}'" for v in values)
    op.execute(
        f"""
        DO $$ BEGIN
            CREATE TYPE "tenant"."{type_name}" AS ENUM ({values_sql});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Enum types ────────────────────────────────────────────────────────
    _create_enum(conn, schema, "folio_item_category", _FOLIO_ITEM_CATEGORY_VALUES)
    _create_enum(conn, schema, "vehicle_inspection_type", _VEHICLE_INSPECTION_TYPE_VALUES)
    _create_enum(conn, schema, "vehicle_fuel_level", _VEHICLE_FUEL_LEVEL_VALUES)

    # ── 2. folio_items (Hospitality) ─────────────────────────────────────────
    # Mirrors app/plugins/hospitality/models/folio.py::FolioItem exactly.
    # No FK on case_id — the plugin's DECOUPLING CONTRACT links to the Case by
    # value ("no FK to core tables"), so none is added here on purpose.
    if not _table_exists(conn, schema, "folio_items"):
        op.create_table(
            "folio_items",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column(
                "category",
                postgresql.ENUM(
                    *_FOLIO_ITEM_CATEGORY_VALUES,
                    name="folio_item_category",
                    schema=schema,
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
            sa.Column("quantity", sa.Numeric(10, 3), nullable=False, server_default=sa.text("1")),
            sa.Column("unit_price", sa.Numeric(14, 4), nullable=False),
            sa.Column(
                "amount", sa.Numeric(14, 4), nullable=False,
                comment="quantity × unit_price; negative for discounts and deposits",
            ),
            sa.Column(
                "currency", sqlmodel.sql.sqltypes.AutoString(length=3),
                nullable=False, server_default="EGP",
            ),
            sa.Column(
                "charge_date", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column(
                "posted_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column("posted_by", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            schema=schema,
        )
        op.create_index("ix_folio_items_case_id", "folio_items", ["case_id"], schema=schema)
        op.create_index(
            "ix_folio_items_case_date", "folio_items",
            ["case_id", "charge_date"], schema=schema,
        )
    else:
        _ensure_column_enum_in_schema(
            conn, schema, "folio_items", "category", "folio_item_category",
        )

    # ── 3. vehicle_inspections (Rental) ──────────────────────────────────────
    # Mirrors app/plugins/rental/models/inspection.py::VehicleInspection exactly,
    # including the UNIQUE (case_id, inspection_type) index that enforces
    # "one pickup + one return inspection per rental case".
    if not _table_exists(conn, schema, "vehicle_inspections"):
        op.create_table(
            "vehicle_inspections",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.Column(
                "inspection_type",
                postgresql.ENUM(
                    *_VEHICLE_INSPECTION_TYPE_VALUES,
                    name="vehicle_inspection_type",
                    schema=schema,
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("mileage", sa.Numeric(10, 0), nullable=False),
            sa.Column(
                "fuel_level",
                postgresql.ENUM(
                    *_VEHICLE_FUEL_LEVEL_VALUES,
                    name="vehicle_fuel_level",
                    schema=schema,
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("damage_notes", sa.JSON(), nullable=True),
            sa.Column("inspected_by", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
            sa.Column(
                "inspected_at", sa.DateTime(timezone=True),
                server_default=sa.text("now()"), nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            schema=schema,
        )
        op.create_index(
            "ix_vehicle_inspections_case_id", "vehicle_inspections",
            ["case_id"], schema=schema,
        )
        op.create_index(
            "ix_vehicle_inspections_case_type", "vehicle_inspections",
            ["case_id", "inspection_type"], unique=True, schema=schema,
        )
    else:
        _ensure_column_enum_in_schema(
            conn, schema, "vehicle_inspections", "inspection_type", "vehicle_inspection_type",
        )
        _ensure_column_enum_in_schema(
            conn, schema, "vehicle_inspections", "fuel_level", "vehicle_fuel_level",
        )


def downgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if _table_exists(conn, schema, "vehicle_inspections"):
        op.drop_index("ix_vehicle_inspections_case_type", "vehicle_inspections", schema=schema)
        op.drop_index("ix_vehicle_inspections_case_id", "vehicle_inspections", schema=schema)
        op.drop_table("vehicle_inspections", schema=schema)

    if _table_exists(conn, schema, "folio_items"):
        op.drop_index("ix_folio_items_case_date", "folio_items", schema=schema)
        op.drop_index("ix_folio_items_case_id", "folio_items", schema=schema)
        op.drop_table("folio_items", schema=schema)

    for type_name in ("vehicle_fuel_level", "vehicle_inspection_type", "folio_item_category"):
        if _type_exists(conn, schema, type_name):
            op.execute(f'DROP TYPE "tenant"."{type_name}"')
