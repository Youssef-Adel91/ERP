"""fix_hr_employees_status_schema

Revision ID: x4s9t0u1v2w3
Revises: w3r8s9t0u1v2
Create Date: 2026-09-02 21:10:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed follow-up bug after w3r8s9t0u1v2 (which created the missing
`employeestatus` enum type). `POST /api/v1/hr/employees` still 500s, now
with a DIFFERENT error:

    asyncpg.exceptions.DatatypeMismatchError: column "status" is of type
    employeestatus but expression is of type
    tenant_<id>.employeestatus
    HINT:  You will need to rewrite or cast the expression.

Root cause: w3r8s9t0u1v2's guard for step 2 ("convert hr_employees.status
to the enum if not already converted") compared only the bare type name
via `information_schema.columns.udt_name`, which does NOT include the
schema. For this tenant, `hr_employees.status` was already pointing at a
type literally named `employeestatus` — but one created in the WRONG
namespace (the connection's default/public schema) by the original,
self-documented-as-buggy `99f91dd227cd_add_missing_tenant_models.py` run.
Since `udt_name == "employeestatus"` already, w3r8s9t0u1v2's guard treated
the column as "already converted" and skipped the `ALTER COLUMN`. Its
step 1 correctly created a SECOND, distinct `employeestatus` type inside
the real tenant schema (its `_type_exists` check IS schema-scoped) — so
two same-named enum types now coexist in different namespaces, the column
points at the old/wrong one, and the app's explicitly schema-qualified
cast points at the new/right one. Postgres treats them as different types
because they are (different OIDs), even though `udt_name` alone couldn't
tell them apart.

Fix: re-check using `information_schema.columns.udt_schema` (which DOES
distinguish namespace) instead of `udt_name`, and force the `ALTER COLUMN`
whenever the column's current type does not live in this tenant's own
schema — regardless of what the bare type name looks like. Idempotent:
safe to re-run, no-op once the column is correctly pointed at
`<tenant_schema>.employeestatus`.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "x4s9t0u1v2w3"
down_revision: Union[str, None] = "w3r8s9t0u1v2"
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


def _column_udt_schema(conn, schema: str, table: str, column: str) -> str | None:
    return conn.execute(
        sa.text(
            "SELECT udt_schema FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _table_exists(conn, schema, "hr_employees"):
        return

    udt_schema = _column_udt_schema(conn, schema, "hr_employees", "status")
    # Only force the ALTER if the column's enum type is NOT already living
    # in this tenant's own schema (covers both "still varchar" — udt_schema
    # is NULL for non-enum types read this way is fine, ALTER handles it —
    # and "pointing at a same-named type in the wrong namespace").
    if udt_schema != schema:
        op.execute(
            'ALTER TABLE "tenant"."hr_employees" '
            'ALTER COLUMN status TYPE "tenant"."employeestatus" '
            'USING status::text::"tenant"."employeestatus"'
        )


def downgrade() -> None:
    # Not reversible — see w3r8s9t0u1v2/q7l2m3n4o5p6 for the same
    # rationale: the column should always have pointed at this tenant's
    # own employeestatus type; reverting would just reintroduce the 500.
    pass
