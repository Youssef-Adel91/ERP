"""
p1_item3_result_and_restore.py — two things in one:

1) Prints the true backend state of the "P1 Item3 Test Take2" checkout
   (the one done through the real browser UI while the hospitality revenue
   account was deliberately broken) — case.data / _legacy_gl and any
   gl_postings row, to compare against what the UI showed the user (a
   clean "تم تسجيل المغادرة" checked-out status with zero error/warning).

2) Restores hospitality's revenue_gl_account back to the real "4010"
   (same as `toggle_hospitality_break.py restore`, folded in here so this
   is the one script to run after the browser test).

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe p1_item3_result_and_restore.py
"""
import asyncio
import uuid

TENANT_ID = uuid.UUID("e1ee4d0e-e8d7-4d5d-9778-c8954687e63f")


async def main() -> None:
    from sqlalchemy import select

    from app.core.db.database import tenant_session
    from app.modules.accounting.models.posting import GLPosting
    from app.modules.cases.models.core import Case, CaseType

    async with tenant_session(TENANT_ID) as session:
        print("=" * 70)
        print("1) True backend state of the Item 3 test checkout")
        print("=" * 70)
        result = await session.execute(select(Case))
        target = None
        for c in result.scalars().all():
            if (c.data or {}).get("guest_name") == "P1 Item3 Test Take2":
                target = c
                break

        if target is None:
            print("  Could not find the test case by guest_name — did the booking go through?")
        else:
            print(f"  case id: {target.id}")
            print(f"  current_stage: {target.current_stage}")
            print(f"  case.data: {target.data}")

            gp = await session.execute(
                select(GLPosting).where(GLPosting.source_id == target.id)
            )
            postings = gp.scalars().all()
            print(f"  gl_postings rows for this case: {len(postings)}")
            for p in postings:
                print(f"    entry_kind={p.entry_kind} status={p.status} "
                      f"error_type={p.error_type} error_message={p.error_message}")

        print()
        print("=" * 70)
        print("2) Restoring hospitality revenue_gl_account back to 4010")
        print("=" * 70)
        result2 = await session.execute(
            select(CaseType).where(CaseType.plugin_key == "hospitality")
        )
        for ct in result2.scalars().all():
            meta = dict(ct.meta or {})
            before = meta.get("revenue_gl_account")
            meta["revenue_gl_account"] = "4010"
            ct.meta = meta
            session.add(ct)
            print(f"  CaseType id={ct.id}: revenue_gl_account {before!r} -> '4010'")

        await session.commit()
        print("  Restored.")


if __name__ == "__main__":
    asyncio.run(main())
