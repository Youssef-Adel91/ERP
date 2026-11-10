#!/usr/bin/env python3
"""
verify_p1_final_smoke_test.py

Smoke test: for four known journal-entry reference/invoice prefixes,
verify that each journal entry's transaction lines are balanced
(sum(debit) == sum(credit)).

Uses a plain raw-SQL asyncpg connection via SQLAlchemy's async engine
against the tenant's dedicated Postgres schema. This is a read-only
diagnostic script, so schema-qualified raw SQL is used directly instead
of the ORM's schema_translate_map / tenant_session() pattern (see
app/core/db/database.py for the canonical ORM mechanism).

Usage (from backend/, same venv as the other verify_*.py scripts):
    python verify_p1_final_smoke_test.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
TENANT_SCHEMA = "tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f"

PREFIXES = [
    "HOSP-01A0A733",
    "TRV-01A0A735",
    "RENT-01A0A73A",
    "REC-01A0A73E",
]

FIND_ENTRIES_SQL = text(
    f'''
    SELECT id, reference, invoice_number, status
    FROM "{TENANT_SCHEMA}".journal_entries
    WHERE reference LIKE :pattern OR invoice_number LIKE :pattern
    ORDER BY id
    '''
)

SUM_LINES_SQL = text(
    f'''
    SELECT
        COALESCE(SUM(debit), 0) AS debit_total,
        COALESCE(SUM(credit), 0) AS credit_total
    FROM "{TENANT_SCHEMA}".transaction_lines
    WHERE journal_entry_id = :entry_id
    '''
)


async def main() -> int:
    engine = create_async_engine(DATABASE_URL)
    overall_pass = True
    found_any = False

    try:
        async with engine.connect() as conn:
            for prefix in PREFIXES:
                print(f"\n=== Prefix: {prefix} ===")
                pattern = f"%{prefix}%"
                result = await conn.execute(FIND_ENTRIES_SQL, {"pattern": pattern})
                entries = result.mappings().all()

                if not entries:
                    print(f"  No journal_entries found for pattern '{pattern}'. FAIL")
                    overall_pass = False
                    continue

                for entry in entries:
                    found_any = True
                    sums = await conn.execute(SUM_LINES_SQL, {"entry_id": entry["id"]})
                    row = sums.mappings().one()
                    debit_total = row["debit_total"]
                    credit_total = row["credit_total"]
                    balanced = debit_total == credit_total
                    if not balanced:
                        overall_pass = False

                    print(f"  Entry id:        {entry['id']}")
                    print(f"  Reference:       {entry['reference']}")
                    print(f"  Invoice number:  {entry['invoice_number']}")
                    print(f"  Status:          {entry['status']}")
                    print(f"  Debit total:     {debit_total}")
                    print(f"  Credit total:    {credit_total}")
                    print(f"  Balanced:        {'PASS' if balanced else 'FAIL'}")
    finally:
        await engine.dispose()

    if not found_any:
        overall_pass = False

    print("\n" + "=" * 40)
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
    print("=" * 40)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
