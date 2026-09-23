"""
verify_gl_postings.py — live verification for P1 Items 1+2 (gl_postings
idempotency guard), run directly against the same DB the app itself uses.

v2 fix: section (A) used raw pg_catalog SQL (fine, unqualified system
catalog names always resolve). Sections (B)/(C) in v1 used a raw
`text("... FROM gl_postings ...")` with no schema prefix — and raw text()
statements are NOT rewritten by tenant_session()'s schema_translate_map
(only ORM/Core-compiled, schema-tagged objects are — same class of gotcha
documented in alembic/tenant/env.py's own module docstring for DDL). That
produced `UndefinedTableError: relation "gl_postings" does not exist` even
though (A) had just proven the table exists in the tenant schema. Fixed here
by using the real ORM model (`select(GLPosting)`), which IS schema-tagged
(schema="tenant" on the model) and gets correctly rewritten.

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe verify_gl_postings.py
"""
import asyncio
import uuid

TENANT_ID = uuid.UUID("e1ee4d0e-e8d7-4d5d-9778-c8954687e63f")


async def main() -> None:
    from sqlalchemy import func, select, text

    from app.core.db.database import tenant_session
    from app.modules.accounting.models.posting import GLPosting
    from app.modules.accounting.services.gl_posting import reserve_posting

    async with tenant_session(TENANT_ID) as session:
        print("=" * 70)
        print("A) Where does gl_postings actually live?")
        print("=" * 70)
        result = await session.execute(text(
            "SELECT n.nspname AS schema_name, c.relname AS table_name "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = 'gl_postings'"
        ))
        for row in result:
            print(f"  table gl_postings -> schema = {row.schema_name}")

        result = await session.execute(text(
            "SELECT conname, conrelid::regclass AS on_table, "
            "pg_get_constraintdef(oid) AS definition "
            "FROM pg_constraint WHERE conname = 'uq_gl_postings_source_kind'"
        ))
        for row in result:
            print(f"  constraint {row.conname} on {row.on_table}: {row.definition}")

        print()
        print("=" * 70)
        print("B) Current gl_postings rows for this tenant (via ORM, schema-safe)")
        print("=" * 70)
        result = await session.execute(select(GLPosting).order_by(GLPosting.last_attempt_at))
        rows = [r[0] for r in result.all()]
        for row in rows:
            print(f"  {row.source_type:12s} {str(row.source_id):38s} {row.entry_kind:32s} "
                  f"{row.status.value if hasattr(row.status, 'value') else row.status:9s} "
                  f"inv={row.invoice_number} amount={row.amount}")
        print(f"  -> total rows: {len(rows)}")

        print()
        print("=" * 70)
        print("C) Idempotency proof: retry reserve_posting() on an existing row")
        print("=" * 70)
        if not rows:
            print("  No existing gl_postings rows to test against — skipping.")
            return

        target = rows[0]
        print(f"  Using existing row: source_type={target.source_type} "
              f"source_id={target.source_id} entry_kind={target.entry_kind}")

        def count_stmt():
            return select(func.count()).select_from(GLPosting).where(
                GLPosting.source_type == target.source_type,
                GLPosting.source_id == target.source_id,
                GLPosting.entry_kind == target.entry_kind,
            )

        before_count = (await session.execute(count_stmt())).scalar_one()

        retry_result = await reserve_posting(
            session,
            source_type=target.source_type,
            source_id=target.source_id,
            entry_kind=target.entry_kind,
            invoice_number=target.invoice_number or "RETRY-TEST",
            amount=target.amount or 0,
            currency="EGP",
        )
        await session.commit()

        after_count = (await session.execute(count_stmt())).scalar_one()

        print(f"  reserve_posting() returned: {retry_result!r}")
        print(f"  row count before retry: {before_count}")
        print(f"  row count after retry:  {after_count}")
        if retry_result is None and before_count == after_count:
            print("  RESULT: PASS — retry was skipped cleanly, ledger unchanged.")
        else:
            print("  RESULT: FAIL — retry was NOT skipped, investigate.")


if __name__ == "__main__":
    asyncio.run(main())
