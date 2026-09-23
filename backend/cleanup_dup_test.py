"""
cleanup_dup_test.py — deletes the two DUP-TEST-001 DRAFT journal entries
(the deliberate duplicate-reference regression probe from P1 Item 1), now
that the gl_postings idempotency guard has been proven live.

IMPORTANT: this only removes the two manual DRAFT entries with
reference='DUP-TEST-001'. It does NOT touch any POSTED entry, and does not
touch gl_postings at all (DUP-TEST-001 was never gl_postings-tracked — see
docs/P1_Item1_2_Report.md section 5 for why).

Uses session.delete() on the ORM JournalEntry object so the
`cascade="all, delete-orphan"` relationship to JournalEntryLine removes the
line rows too — no orphaned lines left behind.

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe cleanup_dup_test.py
"""
import asyncio
import uuid

TENANT_ID = uuid.UUID("e1ee4d0e-e8d7-4d5d-9778-c8954687e63f")


async def main() -> None:
    from sqlalchemy import select

    from app.core.db.database import tenant_session
    from app.modules.accounting.models.core import JournalEntry

    async with tenant_session(TENANT_ID) as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.reference == "DUP-TEST-001")
        )
        rows = result.scalars().all()
        print(f"Found {len(rows)} JournalEntry row(s) with reference='DUP-TEST-001'.")
        for row in rows:
            print(f"  deleting id={row.id} status={row.status}")
            if str(row.status).upper() == "POSTED" or (hasattr(row.status, "value") and row.status.value == "POSTED"):
                print(f"  !! REFUSING to delete a POSTED entry ({row.id}) — stopping, this needs a human decision.")
                return
            await session.delete(row)

        await session.commit()
        print(f"Deleted {len(rows)} row(s) and committed.")

        # Re-verify inside the same script (belt-and-braces; the real
        # end-to-end proof is the API call the user runs separately).
        result2 = await session.execute(
            select(JournalEntry).where(JournalEntry.reference == "DUP-TEST-001")
        )
        remaining = result2.scalars().all()
        print(f"Remaining rows with this reference after delete: {len(remaining)} (expect 0).")


if __name__ == "__main__":
    asyncio.run(main())
