"""
backend/scripts/seed_default_accounting_period.py — STOPGAP, TESTING ONLY

WHY THIS EXISTS:
Live-confirmed: journal-entry posting (`create_journal_entry` in
app/modules/accounting/services/journal.py) requires a matching
`tenant.accounting_periods` row covering the entry's date, or it raises
`ClosedPeriodError`. Investigation confirmed accounting-period management
was never built: no migration seeds a period for new tenants, no API
endpoint exists to create/manage one, and no admin/seed script inserts one
either. This blocks every journal-posting flow (cheque deposit/bounce,
and — asynchronously, via the outbox/event-bus worker — purchase order
receipts, bills, payments, sales invoices, credit notes, stock takes) for
every tenant, always.

This script is an explicit, deliberate STOPGAP so Wave 1 functional
testing (specifically: cheque deposit → bounce → reversing journal entry)
can proceed. It is NOT the real fix — proper accounting-period management
(creation, closing, rollover, an admin/API surface, presumably scoped per
fiscal month/year) is a genuine missing feature that should be scoped and
built separately. This script exists to unblock testing only.

It idempotently inserts ONE wide-open accounting period (2000-01-01 to
2100-12-31, is_closed=False) into every tenant schema that doesn't
already have at least one period row — safe to re-run.

Usage (from backend/, with .venv activated):
    python scripts/seed_default_accounting_period.py
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import uuid6
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, future=True)

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'")
        )
        schemas = [row[0] for row in result.all()]

    print(f"Found {len(schemas)} tenant schemas.")

    seeded: list[str] = []
    skipped: list[str] = []

    for schema in schemas:
        async with engine.begin() as conn:
            # Real schema name is interpolated directly into fully-qualified
            # identifiers below (never SET search_path — see the PgBouncer
            # warning in app/core/db/base.py; this script uses a one-shot
            # connection anyway, but staying consistent avoids ever copying
            # the unsafe pattern elsewhere).
            table_exists = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_name = 'accounting_periods'"
                ),
                {"schema": schema},
            )
            if not table_exists.scalar():
                print(f"  - {schema}: no accounting_periods table yet, skipping.")
                skipped.append(schema)
                continue

            existing = await conn.execute(
                text(f'SELECT 1 FROM "{schema}".accounting_periods LIMIT 1')
            )
            if existing.scalar():
                print(f"  - {schema}: already has at least one period, skipping.")
                skipped.append(schema)
                continue

            period_id = uuid6.uuid7()
            now = datetime.now(timezone.utc)
            await conn.execute(
                text(
                    f'INSERT INTO "{schema}".accounting_periods '
                    "(id, created_at, updated_at, name, start_date, end_date, is_closed) "
                    "VALUES (:id, :created_at, :updated_at, :name, :start_date, :end_date, false)"
                ),
                {
                    "id": period_id,
                    "created_at": now,
                    "updated_at": now,
                    "name": "Open Period (stopgap — not real period management)",
                    # start_date/end_date are TIMESTAMP WITHOUT TIME ZONE on
                    # the AccountingPeriod model (plain `datetime`, no
                    # sa_type override) — pass naive datetimes, unlike
                    # created_at/updated_at above which ARE tz-aware.
                    "start_date": datetime(2000, 1, 1),
                    "end_date": datetime(2100, 12, 31),
                },
            )
            print(f"  - {schema}: seeded wide-open accounting period.")
            seeded.append(schema)

    await engine.dispose()

    print("\n--- Summary ---")
    print(f"Seeded ({len(seeded)}): {', '.join(seeded) if seeded else '(none)'}")
    print(f"Skipped ({len(skipped)}): {', '.join(skipped) if skipped else '(none)'}")


if __name__ == "__main__":
    asyncio.run(main())
