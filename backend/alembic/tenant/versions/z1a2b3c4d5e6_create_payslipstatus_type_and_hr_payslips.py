"""create_payslipstatus_type_and_hr_payslips

Revision ID: y5t0u1v2w3x4
Revises: n5o6p7q8r9s0
Create Date: 2026-09-23 00:00:00.000000+00:00

WHY THIS EXISTS:
Live-reproduced: `GET /api/v1/hr/payslips` 500s for every tenant with
a generic "حدث خطأ غير متوقع" error. Root cause is the exact same class
of bug already fixed twice in this file's sibling models (see
w3r8s9t0u1v2_create_employeestatus_type.py and the LeaveRequestStatus
note next to it in app/modules/hr/models/core.py): `Payslip.status` was
declared as a bare `PayslipStatus` field with no explicit
`sa_column=Column(sa.Enum(..., schema="tenant", create_type=False))`.
SQLModel/SQLAlchemy then auto-generates an unqualified `sa.Enum(PayslipStatus)`
for the column, which does not reliably resolve against
`schema_translate_map={"tenant": <real_schema>}` the way the explicitly
schema-qualified enums elsewhere in this codebase do.

This migration is idempotent and handles both possible states a tenant
schema can be in:

  1. A tenant provisioned via the create_all() fast path (see
     app/core/db/database.py's `provision_tenant_schema`) — `hr_payslips`
     already exists (Payslip.__table__ IS in that function's hand-maintained
     `tenant_tables` list), but its `status` column may be bound to a
     `payslipstatus` type that isn't properly schema-qualified. We convert
     the column to the schema-qualified type.
  2. A tenant that only ever ran the alembic chain directly (no create_all
     fast path) — `hr_payslips` was NEVER created by any migration (grep
     confirms no other file in alembic/tenant/versions/ creates it), so the
     table doesn't exist at all. We create it from scratch, matching the
     Payslip model in app/modules/hr/models/core.py exactly (same column
     set/types as the sibling hr_employees creation in
     99f91dd227cd_add_missing_tenant_models.py).

Same idempotent helper pattern as w3r8s9t0u1v2 (_type_exists/_table_exists/
_column_udt_name) — safe to re-run, safe regardless of which of the two
states above a given tenant is in.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "z1a2b3c4d5e6"
down_revision: Union[str, None] = "n5o6p7q8r9s0"
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


_PAYSLIP_STATUS_VALUES = ("DRAFT", "APPROVED", "PAID")


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Create the missing enum type (idempotent) ──────────────────────
    if not _type_exists(conn, schema, "payslipstatus"):
        values_sql = ", ".join(f"'{v}'" for v in _PAYSLIP_STATUS_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."payslipstatus" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── 2. Create hr_payslips if it genuinely doesn't exist (tenants that
    #        only ever ran the alembic chain, never the create_all fast
    #        path) ─────────────────────────────────────────────────────────
    if not _table_exists(conn, schema, "hr_payslips"):
        op.create_table(
            "hr_payslips",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("employee_id", sa.Uuid(), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("basic_wage", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("allowances", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("deductions", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("net_pay", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(*_PAYSLIP_STATUS_VALUES, name="payslipstatus", schema="tenant", create_type=False),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["employee_id"], ["tenant.hr_employees.id"]),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_hr_payslips_employee_id"), "hr_payslips", ["employee_id"], schema="tenant",
        )
        return  # freshly created with the right type already — nothing left to convert

    # ── 3. Table already existed (create_all fast path) — convert `status`
    #        to the schema-qualified enum type if it isn't already. ───────
    udt_name = _column_udt_name(conn, schema, "hr_payslips", "status")
    if udt_name is not None and udt_name != "payslipstatus":
        op.execute(
            'ALTER TABLE "tenant"."hr_payslips" '
            'ALTER COLUMN status TYPE "tenant"."payslipstatus" '
            f'USING status::text::"tenant"."payslipstatus"'
        )


def downgrade() -> None:
    # Not reversible — same rationale as w3r8s9t0u1v2/x4s9t0u1v2w3: this
    # type and table should have existed since Payslip was first added;
    # reverting would just reintroduce the live 500.
    pass
