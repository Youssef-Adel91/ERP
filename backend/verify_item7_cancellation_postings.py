"""
verify_item7_cancellation_postings.py — P1 Item 7: live DB-level proof of the
cancellation posting mechanics for BOTH real, live-cancelled bookings created
this session:

  1) Hospitality booking "P1 Item7 Hospitality Cancel Test"
     case_id = 01a0a6a3-6594-7fda-b874-ed58922e6a2c
     Cancelled BEFORE check-in (never had a checkout/revenue posting), no
     penalty amount entered in the cancel form.

  2) Travel booking "P1 Item7 Travel Cancel Take2"
     case_id = 01a0a6a9-0dad-7d81-93a2-13bba51a5d11
     Cancelled AFTER being moved to "confirmed" stage, with a
     penalty_amount = 500 EGP entered in the cancel form. The UI's
     journal-entries page already showed a POSTED entry
     "JE-TRV-01A0A6A9-PENALTY" (debit AR 500 / credit Sales Revenue 4010
     500) with description "Sales invoice for P1 Item7 Travel Cancel Take2
     — TRV-01A0A6A9-PENALTY" — this script confirms the underlying
     gl_postings row and its entry_kind/status/source linkage directly.

Also prints ALL gl_postings rows for both case ids (not just the ones the
journal-entries UI happened to render), so nothing is missed if there is a
separate reversal-only posting with no journal entry rendered, or vice
versa.

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe verify_item7_cancellation_postings.py
"""
import asyncio
import uuid

TENANT_ID = uuid.UUID("e1ee4d0e-e8d7-4d5d-9778-c8954687e63f")

HOSPITALITY_CASE_ID = uuid.UUID("01a0a6a3-6594-7fda-b874-ed58922e6a2c")
TRAVEL_CASE_ID = uuid.UUID("01a0a6a9-0dad-7d81-93a2-13bba51a5d11")


async def dump_case_and_postings(session, label: str, case_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from app.modules.accounting.models.posting import GLPosting
    from app.modules.cases.models.core import Case

    print("=" * 70)
    print(f"{label}  (case_id={case_id})")
    print("=" * 70)

    cres = await session.execute(select(Case).where(Case.id == case_id))
    case = cres.scalar_one_or_none()
    if case is None:
        print("  !! Case not found by id — did the id get pasted correctly?")
        return

    print(f"  current_stage: {case.current_stage}")
    print(f"  case.data: {case.data}")
    print()

    pres = await session.execute(
        select(GLPosting).where(GLPosting.source_id == case_id).order_by(GLPosting.created_at)
    )
    postings = pres.scalars().all()
    print(f"  gl_postings rows for this case: {len(postings)}")
    for p in postings:
        print(
            f"    id={p.id}\n"
            f"      source_type={p.source_type} entry_kind={p.entry_kind}\n"
            f"      status={p.status} invoice_number={getattr(p, 'invoice_number', None)}\n"
            f"      amount={getattr(p, 'amount', None)} currency={getattr(p, 'currency', None)}\n"
            f"      journal_entry_id={getattr(p, 'journal_entry_id', None)}\n"
            f"      error_type={getattr(p, 'error_type', None)} error_message={getattr(p, 'error_message', None)}\n"
            f"      created_at={getattr(p, 'created_at', None)}"
        )
    if not postings:
        print("    (none found)")
    print()


async def main() -> None:
    from app.core.db.database import tenant_session

    async with tenant_session(TENANT_ID) as session:
        await dump_case_and_postings(
            session,
            "1) Hospitality cancellation (pre-checkin, no penalty entered)",
            HOSPITALITY_CASE_ID,
        )
        await dump_case_and_postings(
            session,
            "2) Travel cancellation Take2 (post-confirm, penalty=500 EGP)",
            TRAVEL_CASE_ID,
        )

    print("=" * 70)
    print("Interpretation guide")
    print("=" * 70)
    print(
        "  - Hospitality case: EXPECT 0 gl_postings rows. It was cancelled before\n"
        "    check-in/checkout, so no revenue was ever posted for it, and no penalty\n"
        "    amount was entered in the cancel form — there is nothing to reverse and\n"
        "    nothing to charge. 0 rows here would be CORRECT/EXPECTED, not a bug.\n"
        "  - Travel case: EXPECT >=1 gl_postings row with an entry_kind that reflects\n"
        "    the penalty charge (the journal-entries UI already showed a POSTED entry\n"
        "    'JE-TRV-01A0A6A9-PENALTY' debiting Accounts Receivable 500 / crediting\n"
        "    Sales Revenue 500 EGP, described as 'Sales invoice for P1 Item7 Travel\n"
        "    Cancel Take2'). This script's job is to confirm the gl_postings row\n"
        "    itself (source_type/entry_kind/status/journal_entry_id), which the UI\n"
        "    alone does not expose."
    )


if __name__ == "__main__":
    asyncio.run(main())
