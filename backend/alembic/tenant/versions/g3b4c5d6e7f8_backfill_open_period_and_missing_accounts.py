"""backfill_open_period_and_missing_accounts

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-15 00:00:00.000000+00:00

WHY THIS EXISTS (live-confirmed, 15 Sep 2026)
----------------------------------------------
With `folio_items` / `vehicle_inspections` created (f2a3b4c5d6e7), all four
verticals finally published their revenue events — and the ledger was STILL
empty. The raw exception, captured from backend/logs/backend.log after
app/modules/accounting/events.py was changed to re-raise instead of swallowing:

    app.core.events.event_bus  ERROR
    handler 'handle_invoice_created' raised while processing
    event_type='invoice.created' event_id=8ff8f896-...
    ClosedPeriodError("No accounting period defined for entry date
                       '2026-09-15'. Cannot post journal entry.")

create_journal_entry() (app/modules/accounting/services/journal.py) HARD-BLOCKS
every posting unless an AccountingPeriod row covers entry_date. Two gaps, both
affecting only tenants provisioned before the corresponding fix shipped — and
nothing ever backfilled them, so those tenants can never post a journal entry:

  1. NO AccountingPeriod ROW.
     app/core/db/database.py::_provision_tenant_schema_internal seeds a wide-open
     2020–2099 period ("Step 3b"), but only for tenants provisioned after that
     step was added. Older tenants have the accounting_periods TABLE (the SELECT
     above succeeded — it returned zero rows, hence ClosedPeriodError rather than
     UndefinedTableError) and no row in it.

  2. MISSING CHART-OF-ACCOUNTS ROWS.
     Live check of tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f returned:
        ["1100","1200","1300","2100","3100","4010","5010","5100"]
     — no "4020". DEFAULT_ACCOUNTS gained 4020 ("Vehicle Rental Revenue") after
     that tenant was provisioned, and the rental CaseType.meta points
     revenue_gl_account at exactly "4020", so every vehicle-return posting in an
     older tenant dies with LookupError("Account with code '4020' not found.")
     the moment the period block above is cleared.

Both are pure data backfills, both idempotent, and both are safe on a tenant
that already has the rows (nothing is inserted). Matches the seed values in
app/modules/accounting/models/core.py::DEFAULT_ACCOUNTS and the "Open Period"
seeded by provisioning, so a backfilled tenant ends up identical to a new one.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror of app/modules/accounting/models/core.py::DEFAULT_ACCOUNTS
# (code, name, name_ar, account_type, is_system)
_DEFAULT_ACCOUNTS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("1100", "Cash & Cash Equivalents", "النقدية وما يعادلها", "ASSET", True),
    ("1200", "Accounts Receivable", "العملاء (حسابات مدينة)", "ASSET", True),
    ("1300", "Inventory", "المخزون", "ASSET", False),
    ("2100", "Accounts Payable", "الموردون (حسابات دائنة)", "LIABILITY", True),
    ("3100", "Owner's Equity", "حقوق الملكية", "EQUITY", True),
    ("4010", "Sales Revenue", "إيرادات المبيعات", "REVENUE", True),
    ("4020", "Vehicle Rental Revenue", "إيرادات تأجير المركبات", "REVENUE", True),
    ("5010", "Cost of Goods Sold", "تكلفة البضاعة المباعة", "EXPENSE", False),
    ("5100", "Operating Expenses", "المصروفات التشغيلية", "EXPENSE", False),
)


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
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = :table"
            ),
            {"schema": schema, "table": table},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    schema = _get_schema()

    # ── 1. Wide-open accounting period ───────────────────────────────────────
    # Deliberately 2020–2099, identical to what provisioning seeds: a missing
    # period blocks ALL automated GL posting, and an over-wide open period is
    # far less harmful than a permanently unpostable ledger. An OWNER/ADMIN can
    # close/split periods later through the accounting UI.
    if _table_exists(conn, schema, "accounting_periods"):
        existing = conn.execute(
            sa.text(f'SELECT COUNT(*) FROM "{schema}".accounting_periods')
        ).scalar()
        if not existing:
            conn.execute(
                sa.text(
                    f'INSERT INTO "{schema}".accounting_periods '
                    "(id, created_at, updated_at, name, start_date, end_date, is_closed) "
                    "VALUES (:id, now(), now(), :name, :start_date, :end_date, false)"
                ),
                {
                    "id": uuid.uuid4(),
                    "name": "Open Period",
                    # asyncpg binds TIMESTAMP params strictly: it requires real
                    # datetime objects and raises DataError on ISO strings.
                    "start_date": datetime(2020, 1, 1, 0, 0, 0),
                    "end_date": datetime(2099, 12, 31, 23, 59, 59),
                },
            )

    # ── 2. Missing chart-of-accounts rows ────────────────────────────────────
    # Insert only codes this tenant does not already have (accounts.code carries
    # UNIQUE uq_accounts_code, so re-running can never duplicate).
    if _table_exists(conn, schema, "accounts"):
        present = {
            row[0]
            for row in conn.execute(sa.text(f'SELECT code FROM "{schema}".accounts')).fetchall()
        }
        for code, name, name_ar, account_type, is_system in _DEFAULT_ACCOUNTS:
            if code in present:
                continue
            conn.execute(
                sa.text(
                    f'INSERT INTO "{schema}".accounts '
                    "(id, created_at, updated_at, code, name, name_ar, account_type, "
                    " is_control, is_active, is_system) "
                    "VALUES (:id, now(), now(), :code, :name, :name_ar, "
                    f' CAST(:account_type AS "{schema}".accounttype), false, true, :is_system)'
                ),
                {
                    "id": uuid.uuid4(),
                    "code": code,
                    "name": name,
                    "name_ar": name_ar,
                    "account_type": account_type,
                    "is_system": is_system,
                },
            )


def downgrade() -> None:
    # Intentionally not reversible: both inserts are baseline data that every
    # tenant was always supposed to have (provisioning seeds exactly these for
    # new tenants). Removing them would only restore the unpostable-ledger bug,
    # and deleting a period or a system account a tenant may have since posted
    # against would be destructive.
    pass
