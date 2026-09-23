"""create_supplierpaymentstatus_type

Revision ID: z3c4d5e6f7g8
Revises: z2b3c4d5e6f7
Create Date: 2026-09-23 00:10:00.000000+00:00

WHY THIS EXISTS:
Same bug class as z1a2b3c4d5e6/z2b3c4d5e6f7: `SupplierPayment.status` used
`sa_column=Column(sa.Enum(SupplierPaymentStatus), nullable=False)` -- an
explicit sa.Enum() call, but still with no `schema="tenant"` /
`create_type=False`, so it has exactly the same failure mode as the other
bare enums fixed in this chain (found via static scan of every TenantBase
model's enum-typed fields, not yet live-reproduced against a populated
supplier_payments table the way payslips/import_dossiers were, since this
tenant has no supplier payments recorded yet -- but the code pattern is
unambiguous and matches the confirmed-broken cases exactly, so it is fixed
proactively here rather than waiting for a live 500 to prove it).

Idempotent: creates the type if missing, converts the column if the table
already exists with the wrong (unqualified) type, does nothing otherwise.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "z3c4d5e6f7g8"
down_revision: Union[str, None] = "z2b3c4d5e6f7"
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


_SUPPLIER_PAYMENT_STATUS_VALUES = ("DRAFT", "POSTED", "CANCELLED")


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _type_exists(conn, schema, "supplierpaymentstatus"):
        values_sql = ", ".join(f"'{v}'" for v in _SUPPLIER_PAYMENT_STATUS_VALUES)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE "tenant"."supplierpaymentstatus" AS ENUM ({values_sql});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    if _table_exists(conn, schema, "supplier_payments"):
        udt_name = _column_udt_name(conn, schema, "supplier_payments", "status")
        if udt_name is not None and udt_name != "supplierpaymentstatus":
            # The existing column has a server-side DEFAULT bound to the old
            # (bare/unqualified) enum type -- Postgres cannot auto-cast a
            # column default across an ALTER COLUMN TYPE, so it must be
            # dropped first and re-added against the new type afterward.
            op.execute('ALTER TABLE "tenant"."supplier_payments" ALTER COLUMN status DROP DEFAULT')
            op.execute(
                'ALTER TABLE "tenant"."supplier_payments" '
                'ALTER COLUMN status TYPE "tenant"."supplierpaymentstatus" '
                'USING status::text::"tenant"."supplierpaymentstatus"'
            )
            op.execute(
                'ALTER TABLE "tenant"."supplier_payments" '
                'ALTER COLUMN status SET DEFAULT \'DRAFT\'::"tenant"."supplierpaymentstatus"'
            )


def downgrade() -> None:
    pass
