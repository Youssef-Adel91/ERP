"""
verify_reserve_rollback.py — live proof of gl_postings binding condition #3:
reserve_posting() + create_journal_entry() must be in the SAME transaction,
so a crash between them leaves NO orphan reservation.

Simulates exactly that: opens a transaction, calls the real reserve_posting()
on a brand-new (never-used) source_id, deliberately raises before any
create_journal_entry() call, lets the session roll back, then checks with a
FRESH session/transaction whether the reservation survived.

Expected (PASS): the row is gone after rollback — reserve+post really is
one atomic unit.
Danger (FAIL): the row is still there as RESERVED — that's a live orphan-
reservation bug (it would permanently block any future real posting attempt
for that exact source, since the UNIQUE constraint would consider it
already claimed forever).

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe verify_reserve_rollback.py
"""
import asyncio
import uuid

TENANT_ID = uuid.UUID("e1ee4d0e-e8d7-4d5d-9778-c8954687e63f")


async def main() -> None:
    from sqlalchemy import select

    from app.core.db.database import tenant_session
    from app.modules.accounting.models.posting import GLPosting
    from app.modules.accounting.services.gl_posting import reserve_posting

    test_source_id = uuid.uuid4()  # guaranteed never used before
    test_entry_kind = "TEST_CRASH_SIMULATION_" + uuid.uuid4().hex[:8]

    print("=" * 70)
    print("STEP 1 — reserve, then deliberately crash BEFORE create_journal_entry()")
    print("=" * 70)
    print(f"  test source_id={test_source_id} entry_kind={test_entry_kind}")

    try:
        async with tenant_session(TENANT_ID) as session:
            reserved = await reserve_posting(
                session,
                source_type="TEST_CRASH_PROBE",
                source_id=test_source_id,
                entry_kind=test_entry_kind,
                invoice_number="CRASH-TEST-001",
                amount=999,
                currency="EGP",
            )
            print(f"  reserve_posting() returned: {reserved!r} (should be a real row, not None)")
            if reserved is None:
                print("  UNEXPECTED: reservation itself failed — aborting test.")
                return

            # Simulate the exact failure this binding condition exists for:
            # a crash/exception AFTER the reservation write but BEFORE the
            # journal entry is created, in the SAME transaction/session.
            print("  Deliberately raising RuntimeError now (before create_journal_entry)...")
            raise RuntimeError("Simulated mid-transaction crash for P1 verification")
    except RuntimeError as exc:
        print(f"  Caught expected simulated crash: {exc}")
        print("  (tenant_session's context manager should have rolled back on exception exit)")

    print()
    print("=" * 70)
    print("STEP 2 — fresh session, check if the reservation survived the rollback")
    print("=" * 70)
    async with tenant_session(TENANT_ID) as session2:
        result = await session2.execute(
            select(GLPosting).where(
                GLPosting.source_type == "TEST_CRASH_PROBE",
                GLPosting.source_id == test_source_id,
                GLPosting.entry_kind == test_entry_kind,
            )
        )
        surviving_row = result.scalar_one_or_none()

    if surviving_row is None:
        print("  No row found — the reservation did NOT survive the rollback.")
        print("  RESULT: PASS — reserve_posting() + create_journal_entry() really are")
        print("          atomic; a crash between them loses the claim too, so a future")
        print("          real retry for this exact source is not permanently blocked.")
    else:
        print(f"  !! FOUND a surviving row: id={surviving_row.id} status={surviving_row.status}")
        print("  RESULT: FAIL — orphan reservation survived a mid-transaction crash.")
        print("          This IS a live bug: this exact source_id/entry_kind is now")
        print("          permanently 'claimed' with no journal entry behind it, and")
        print("          any real future posting attempt for it will be silently")
        print("          skipped forever by the UNIQUE constraint. STOP — do not clean")
        print("          this up silently, report it.")


if __name__ == "__main__":
    asyncio.run(main())
