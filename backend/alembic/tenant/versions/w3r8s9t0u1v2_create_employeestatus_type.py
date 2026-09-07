"""create_employeestatus_type

Revision ID: w3r8s9t0u1v2
Revises: v2q7r8s9t0u1
Create Date: 2026-09-02 00:00:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed bug: `POST /api/v1/hr/employees` 500s for every request on
tenant `tenant_5410d254_bb21_4d00_a153_0acf49945bb4` with:

    asyncpg.exceptions.UndefinedObjectError: type
    "tenant_5410d254_bb21_4d00_a153_0acf49945bb4.employeestatus" does not
    exist

The cast in the failing INSERT is already correctly schema-qualified (the
model's `sa.Enum(EmployeeStatus, name="employeestatus", schema="tenant",
create_type=False)` in app/modules/hr/models/core.py relies on the
schema_translate_map listener to rewrite "tenant" -> the real tenant
schema at query-compile time, same mechanism ShiftStatus/AccountType/etc.
use) — this is NOT a missing-schema-qualifier bug. The type genuinely does
not exist in this tenant's schema.

Root cause, confirmed by reading every migration that touches
`hr_employees`/`employeestatus`:

  - The ONLY place `employeestatus` is ever created is
    99f91dd227cd_add_missing_tenant_models.py. That file's own docstring
    self-documents that it was edited in place, AFTER already being applied
    for at least one live tenant, to fix the type's original bare
    (non-schema-qualified) `CREATE TYPE employeestatus` — which had been
    silently created once in the connection's default (non-tenant) schema
    rather than inside each tenant's own schema.
  - Because Alembic only re-runs a revision's upgrade() for tenants that
    have NOT yet recorded it as applied, any tenant (including
    tenant_5410d254...) that had already migrated past 99f91dd227cd
    *before* that in-place edit never re-ran the fixed CREATE TYPE
    statement. Its `hr_employees` table exists (created in that same
    original migration run), but `employeestatus` was never actually
    created inside its own tenant schema.
  - Unlike the sibling `shiftstatus` type (also created by
    99f91dd227cd), which got a genuine follow-up migration
    (o5j0k1l2m3n4_backfill_purchasing_audit_cols_and_pos.py) that
    idempotently re-asserts the type — added as a brand-new revision, so
    it actually executed for every already-migrated tenant — no equivalent
    follow-up migration was ever written for `employeestatus`. This
    migration is that follow-up, following the exact same pattern already
    used for `purchaseorderstatus` in
    q7l2m3n4o5p6_create_purchaseorderstatus_type.py.

Enum member values match app.modules.hr.models.core.EmployeeStatus exactly
(ACTIVE, ON_LEAVE, TERMINATED) — unchanged from what 99f91dd227cd always
intended to create.

Investigated the other 6 enum types "fixed" earlier this session under the
same missing-schema assumption (Warehouse.type/warehousetype,
Batch.status/batchstatus, SerialNumber.state/serialstate,
StockTake.status/stocktakestatus, StockTransfer.status/transferstatus,
LeaveRequest.status/leaverequeststatus):

  - warehousetype/batchstatus/serialstate/stocktakestatus/transferstatus
    are all created by f93809b48226_phase_1b_step_6_complete_inventory.py,
    which declares them via plain `sa.Enum(..., name=..., schema='tenant')`
    (no create_type=False) directly on the table's column list — letting
    SQLAlchemy's standard automatic checkfirst=True enum-creation event
    emit the CREATE TYPE itself, schema-qualified, before the table is
    created. That file has never been edited since its original commit (no
    self-documented retroactive fix, no later mtime drift the way
    99f91dd227cd/m3h8i9j0k1l2 show), so whatever it did the one time each
    tenant first ran it is exactly what's on disk today — there is no
    edited-after-applied drift risk for these five. Confirmed safe.
  - shiftstatus is confirmed safe as described above (re-asserted by
    o5j0k1l2m3n4, a genuinely new revision every already-migrated tenant
    still had to apply).
  - leaverequeststatus (m3h8i9j0k1l2_add_hr_leave_requests.py) creates its
    enum via `sa.Enum(..., schema=schema_name)` where `schema_name` is
    resolved live from the Alembic context (not a literal "tenant" token
    needing the schema_translate_map rewrite) — correct by construction
    since the file's original authoring, and structurally unlike
    99f91dd227cd's original bug (a completely unqualified `CREATE TYPE`).
    No live 500 has been reported against `/hr/leave-requests`, and no
    self-documented retroactive-fix narrative exists for this file the way
    99f91dd227cd has for employeestatus. Left untouched here — flagged as
    lower-confidence than the other five only because its mtime is close
    in time to 99f91dd227cd's edit, but not included in this migration
    since that alone is not confirmation it is actually broken.

Defensive/idempotent throughout, same helper pattern as
q7l2m3n4o5p6/o5j0k1l2m3n4 (`_type_exists`) — safe to re-run, safe for a
tenant that already has the type and/or the column already converted via
some other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "w3r8s9t0u1v2"
down_revision: Union[str, None] = "v2q7r8s9t0u1"
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


# Exact member values of app.modules.hr.models.core.EmployeeStatus.
_EMPLOYEE_STATUS_VALUES = ("ACTIVE", "ON_LEAVE", "TERMINATED")


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Create the missing enum type ─────────────────────────────────────
    if not _type_exists(conn, schema, "employeestatus"):
        values_sql = ", ".join(f"'{v}'" for v in _EMPLOYEE_STATUS_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."employeestatus" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── 2. Convert hr_employees.status to the enum type the model expects,
    #        if it isn't already (covers the case where the original
    #        99f91dd227cd run for this tenant left the column pointing at
    #        whatever it managed to create, or never converted it). No-op
    #        if the table doesn't exist yet or is already converted. ──────
    if _table_exists(conn, schema, "hr_employees"):
        udt_name = _column_udt_name(conn, schema, "hr_employees", "status")
        if udt_name is not None and udt_name != "employeestatus":
            op.execute(
                'ALTER TABLE "tenant"."hr_employees" '
                'ALTER COLUMN status TYPE "tenant"."employeestatus" '
                'USING status::text::"tenant"."employeestatus"'
            )


def downgrade() -> None:
    # Not reversible — see q7l2m3n4o5p6/o5j0k1l2m3n4 for the same rationale:
    # this type and column conversion should have existed since
    # hr_employees was first created; reverting either would just
    # reintroduce the live 500.
    pass
