"""create_pos_sales_table

Revision ID: u1p6q7r8s9t0
Revises: t0o5p6q7r8s9
Create Date: 2026-08-22 23:45:00.000000+00:00

WHY THIS EXISTS:
Proactive fix before live-testing `POST /api/v1/pos/checkout`. That
handler (app/modules/pos/api.py::checkout) creates a `PosSale` row and
returns its id as `pos_sale_id` in the response — i.e. checkout INSERTs
into `pos_sales` on every successful sale, unconditionally.

Confirmed via full grep of backend/alembic/tenant/versions/ (all file
CONTENTS, not just filenames) for "pos_sales" / "PosSale": the only hit
is a comment in t0o5p6q7r8s9_fix_pos_cash_shifts_timestamp_tz.py
explicitly flagging this as a known, pre-existing, out-of-scope gap —
there is no `op.create_table("pos_sales", ...)` anywhere, under this name
or any other (SQLModel default-naming was also checked: PosSale has an
explicit `__tablename__ = "pos_sales"` in app/modules/pos/models.py, so
there is no carrier-tables-style naming-drift risk here either). So this
is a genuine gap, not a naming/qualification issue: `pos_sales` does not
exist in any tenant schema, and checkout would 500 with
`asyncpg.exceptions.UndefinedTableError` on its very first successful
sale.

Table created column-for-column from `PosSale` in app/modules/pos/models.py:
  - id, created_at, updated_at, created_by, updated_by, deleted_at
    (BaseMixin, app/core/db/base.py) — created_at/updated_at as
    TIMESTAMP WITH TIME ZONE with server_default=now(), matching the
    convention fixed today in r8m3n4o5p6q7 (NOT naive, NOT missing a
    server default).
  - shift_id: FK -> tenant.pos_cash_shifts.id, NOT NULL, indexed.
  - invoice_id: FK -> tenant.sales_invoices.id, NOT NULL, indexed.
  - cashier_id: UUID, NOT NULL, indexed (no FK declared on the model —
    plain UUID column, matching CashShift.opened_by/closed_by which are
    also FK-less UUID columns on the sibling table).
  - amount: NUMERIC(18, 4), NOT NULL.
  - payment_method: VARCHAR(30), NOT NULL, server_default 'cash'
    (matches the model's `Field(default="cash", max_length=30)`).

PosSale declares no Postgres ENUM columns, so — unlike q7l2m3n4o5p6/
99f91dd227cd — this migration creates no new Postgres ENUM types and has
no schema-qualified-enum-cast pitfall to guard against.

Defensive/idempotent via the same `_table_exists` (information_schema)
guard used throughout this chain (n4i9j0k1l2m3's carrier tables, etc.) —
safe to re-run and safe for a tenant that already has this table via some
other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "u1p6q7r8s9t0"
down_revision: Union[str, None] = "t0o5p6q7r8s9"
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

    if not _table_exists(conn, schema, "pos_sales"):
        op.create_table(
            "pos_sales",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("shift_id", sa.Uuid(), nullable=False),
            sa.Column("invoice_id", sa.Uuid(), nullable=False),
            sa.Column("cashier_id", sa.Uuid(), nullable=False),
            sa.Column("amount", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column(
                "payment_method",
                sqlmodel.sql.sqltypes.AutoString(length=30),
                server_default="cash",
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["shift_id"], ["tenant.pos_cash_shifts.id"], name="fk_pos_sales_shift_id_pos_cash_shifts"),
            sa.ForeignKeyConstraint(["invoice_id"], ["tenant.sales_invoices.id"], name="fk_pos_sales_invoice_id_sales_invoices"),
            sa.PrimaryKeyConstraint("id"),
            schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_pos_sales_shift_id"), "pos_sales", ["shift_id"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_pos_sales_invoice_id"), "pos_sales", ["invoice_id"], unique=False, schema="tenant",
        )
        op.create_index(
            op.f("ix_tenant_pos_sales_cashier_id"), "pos_sales", ["cashier_id"], unique=False, schema="tenant",
        )


def downgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if _table_exists(conn, schema, "pos_sales"):
        op.drop_index(op.f("ix_tenant_pos_sales_cashier_id"), table_name="pos_sales", schema="tenant")
        op.drop_index(op.f("ix_tenant_pos_sales_invoice_id"), table_name="pos_sales", schema="tenant")
        op.drop_index(op.f("ix_tenant_pos_sales_shift_id"), table_name="pos_sales", schema="tenant")
        op.drop_table("pos_sales", schema="tenant")
