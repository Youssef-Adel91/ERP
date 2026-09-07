"""drop_sales_invoices_order_id_not_null

Revision ID: v2q7r8s9t0u1
Revises: u1p6q7r8s9t0
Create Date: 2026-08-22 23:55:00.000000+00:00

WHY THIS EXISTS:
Live-confirmed bug: `POST /api/v1/pos/checkout` (which calls
`create_adhoc_invoice()` in app/modules/sales/services/invoicing.py) 500s
with `asyncpg.exceptions.NotNullViolationError: null value in column
"order_id" of relation "sales_invoices" violates not-null constraint`.

Root cause, confirmed by reading the full history:
  - `create_adhoc_invoice()` is explicitly designed to create a SalesInvoice
    with `order_id=None` — it exists specifically for direct/ad-hoc billing
    flows with no preceding SalesOrder (POS walk-in sales, Hospitality folio
    checkout, Vehicle Rental agreement close-out — see the function's own
    docstring and services/invoicing.py::post_invoice's handling of
    `invoice.order_id is not None`).
  - `app/modules/sales/models/invoice.py`'s `SalesInvoice.order_id` is
    ALREADY declared `UUID | None = Field(default=None, ...)` — nullable on
    the Python/model side, with an inline comment explicitly documenting the
    ad-hoc-invoice rationale ("Nullable: service-vertical plugins... the
    model no longer requires it"). Every other call site that reads
    `SalesInvoice.order_id` (sales/services/returns.py, sales/api/invoices.py,
    sales/services/recurring_worker.py, accounting's process_invoice_posted
    via the event payload) already null-checks it correctly.
  - BUT the physical `tenant.sales_invoices.order_id` column, created by
    a1b2c3d4e5f6_add_sales_invoicing.py, is still `nullable=False` — that
    migration predates the ad-hoc-invoicing feature and was never updated
    when the model was relaxed. No migration in the chain ever ran
    `ALTER COLUMN order_id DROP NOT NULL`. Sibling table `sales_returns`
    (b2c3d4e5f6a1_add_sales_returns.py) got this right from the start
    (`order_id` created `nullable=True`), confirming ad-hoc/order-less
    documents were already an accepted pattern by the time returns was
    built — sales_invoices is simply the one table the migration chain
    never caught up on.

Checked for anything else `create_adhoc_invoice()` might be missing: cross-
referenced every column it sets against the full `SalesInvoice` model
(BaseMixin id/created_at/updated_at/created_by/updated_by/deleted_at — all
have Python or server defaults; DocumentLifecycleMixin's `state` has a
Python default; invoice_number/contact_id/status/issue_date/due_date/
currency/subtotal/tax_total/grand_total are all explicitly set by the
function). No other NOT NULL gap found in this path.

Fix: drop the NOT NULL constraint on `sales_invoices.order_id` so ad-hoc
invoices (order_id=None) can actually be inserted, matching the model,
sibling `sales_returns` table, and every reader's null-safe handling.
Defensive/idempotent via the same information_schema `is_nullable` check
used throughout this chain (p6k1l2m3n4o5 etc.) — safe to re-run, safe for
a tenant whose column is already nullable via some other path.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "v2q7r8s9t0u1"
down_revision: Union[str, None] = "u1p6q7r8s9t0"
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


def _column_is_nullable(conn, schema: str, table: str, column: str) -> bool | None:
    result = conn.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()
    if result is None:
        return None
    return result == "YES"


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    if not _table_exists(conn, schema, "sales_invoices"):
        # Fresh/never-provisioned tenant schema — nothing to backfill; the
        # table will be created (by a1b2c3d4e5f6, if still NOT NULL there)
        # and this migration's job is only to relax an existing column.
        # A brand-new tenant still needs this fix, so fall through only if
        # the table genuinely doesn't exist yet (nothing to alter).
        return

    is_nullable = _column_is_nullable(conn, schema, "sales_invoices", "order_id")
    if is_nullable is False:
        op.alter_column(
            "sales_invoices",
            "order_id",
            existing_type=sa.Uuid(),
            nullable=True,
            schema="tenant",
        )


def downgrade() -> None:
    # Not reversible — see p6k1l2m3n4o5/o5j0k1l2m3n4 for the same rationale:
    # `create_adhoc_invoice()` and its callers (POS checkout, Hospitality,
    # Rental) genuinely need order_id=None to be a valid state; restoring
    # NOT NULL would just reintroduce the live bug this migration fixes and
    # would fail outright if any ad-hoc invoice rows already exist.
    pass
