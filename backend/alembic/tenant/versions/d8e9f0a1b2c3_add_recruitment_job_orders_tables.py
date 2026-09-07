"""add_recruitment_job_orders_tables

Revision ID: d8e9f0a1b2c3
Revises: z6c1a2r3r4i5
Create Date: 2026-09-07 00:00:00.000000+00:00

WHY THIS EXISTS:
Wave 3 item 4 (Recruitment / overseas staffing). Unlike the Settlements gap
fixed in z6c1a2r3r4i5, this is NOT a missing-backend situation — a complete
recruitment plugin already exists at app/plugins/recruitment/ (models,
services, API, listeners) and is already wired into main.py's router
registration and the plugin marketplace. The frontend page at
frontend/src/app/dashboard/recruitment/page.tsx already calls every one of
its endpoints and expects the exact response shapes the plugin produces.

The only real gap: app/plugins/recruitment/models/job_orders.py defines
JobOrder (table "recruitment_job_orders") and JobOrderCase (table
"recruitment_job_order_cases"), both TenantBase subclasses with
{"schema": "tenant"} already correctly set — but no migration in this chain
has ever created either table. Confirmed by grepping every file under
alembic/tenant/versions/ for "recruitment"/"job_order"/"candidate_deployment"
— no op.create_table() for either table exists anywhere. `GET
/recruitment/job-orders` would 500 with UndefinedTableError exactly like
Settlements did before z6c1a2r3r4i5.

Both models already inherit TenantBase (app/core/db/base.py), which
supplies id/created_at/updated_at/created_by/updated_by/deleted_at with the
standard server_default=now() pattern — mirrored here from
c7d8e9f0a1b2_add_cheques_table.py's TenantBase column block, which is the
established precedent for migrating a TenantBase-derived table by hand.

JobOrder.status is a plain `str` field (JobOrderStatus is a StrEnum used
only as a Python-side default/validation aid, not a SQLModel native-enum
column — no sa.Enum/Column wrapping in the model), so this migration creates
it as a plain VARCHAR(20), matching the model exactly. No native Postgres
enum type is needed here (unlike Settlements' CarrierSettlementState etc.).

JobOrderCase enforces "one candidate per job order" via a UNIQUE constraint
on case_id (uq_job_order_cases_case in the model) — reproduced here.

Chained directly off z6c1a2r3r4i5 (the current real chain tip as of this
migration's authoring — verified by grepping every versions/*.py file for
its own revision id appearing as someone else's down_revision, finding no
descendants). The separate pre-existing dangling head
(b2c3d4e5f6a1_add_sales_returns.py) documented at length in
z6c1a2r3r4i5's docstring is untouched and still requires targeting this
migration's specific revision id explicitly rather than bare
`upgrade head`/`heads`.

Defensive/idempotent via the same _table_exists (information_schema) guard
used throughout this chain — safe to re-run, safe for a tenant that already
has some of this from a partial prior attempt.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "z6c1a2r3r4i5"
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


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. recruitment_job_orders ────────────────────────────────────────────
    if not _table_exists(conn, schema, "recruitment_job_orders"):
        op.create_table(
            "recruitment_job_orders",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("order_reference", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("sponsor_id", sa.Uuid(), nullable=False),
            sa.Column("required_profession", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
            sa.Column("target_country", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column("target_count", sa.Integer(), nullable=False),
            sa.Column("fulfilled_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), server_default="OPEN", nullable=False),
            sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["sponsor_id"], ["tenant.contacts.id"],
                name="fk_recruitment_job_orders_sponsor_id_contacts",
            ),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_recruitment_job_orders_order_reference"),
            "recruitment_job_orders", ["order_reference"], unique=False, schema="tenant",
        )
        op.create_index(
            "ix_job_orders_sponsor", "recruitment_job_orders", ["sponsor_id"], unique=False, schema="tenant",
        )
        op.create_index(
            "ix_job_orders_status", "recruitment_job_orders", ["status"], unique=False, schema="tenant",
        )
        op.create_index(
            "ix_job_orders_profession", "recruitment_job_orders", ["required_profession"], unique=False, schema="tenant",
        )

    # ── 2. recruitment_job_order_cases ───────────────────────────────────────
    if not _table_exists(conn, schema, "recruitment_job_order_cases"):
        op.create_table(
            "recruitment_job_order_cases",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("job_order_id", sa.Uuid(), nullable=False),
            sa.Column("case_id", sa.Uuid(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["job_order_id"], ["tenant.recruitment_job_orders.id"],
                name="fk_recruitment_job_order_cases_job_order_id",
            ),
            sa.ForeignKeyConstraint(
                ["case_id"], ["tenant.cases.id"],
                name="fk_recruitment_job_order_cases_case_id",
            ),
            sa.UniqueConstraint("case_id", name="uq_job_order_cases_case"),
            schema="tenant",
        )
        op.create_index(
            "ix_tenant_recruitment_job_order_cases_job_order_id",
            "recruitment_job_order_cases", ["job_order_id"], unique=False, schema="tenant",
        )
        op.create_index(
            "ix_tenant_recruitment_job_order_cases_case_id",
            "recruitment_job_order_cases", ["case_id"], unique=False, schema="tenant",
        )


def downgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if _table_exists(conn, schema, "recruitment_job_order_cases"):
        op.drop_index(
            "ix_tenant_recruitment_job_order_cases_case_id",
            table_name="recruitment_job_order_cases", schema="tenant",
        )
        op.drop_index(
            "ix_tenant_recruitment_job_order_cases_job_order_id",
            table_name="recruitment_job_order_cases", schema="tenant",
        )
        op.drop_table("recruitment_job_order_cases", schema="tenant")

    if _table_exists(conn, schema, "recruitment_job_orders"):
        op.drop_index(
            "ix_job_orders_profession", table_name="recruitment_job_orders", schema="tenant",
        )
        op.drop_index(
            "ix_job_orders_status", table_name="recruitment_job_orders", schema="tenant",
        )
        op.drop_index(
            "ix_job_orders_sponsor", table_name="recruitment_job_orders", schema="tenant",
        )
        op.drop_index(
            op.f("ix_tenant_recruitment_job_orders_order_reference"),
            table_name="recruitment_job_orders", schema="tenant",
        )
        op.drop_table("recruitment_job_orders", schema="tenant")
