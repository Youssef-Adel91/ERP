"""
toggle_hospitality_break.py — TEMPORARY, reversible break for a live P1
Item 3 test (does the user actually SEE a posting failure, or does it stay
silent?).

Flips hospitality's CaseType.meta["revenue_gl_account"] between the real
code ("4010") and a nonexistent one ("9999-DOES-NOT-EXIST"), so a checkout
done while broken will hit a real, live account-lookup failure inside
create_journal_entry() — the exact same failure class as the original P0
bug, just deliberately reintroduced for one test run.

This does NOT touch any code file and needs no backend restart — meta lives
in the case_types row in the DB and is read fresh on every checkout.

Usage:
    .\.venv\Scripts\python.exe toggle_hospitality_break.py break     # before the test
    .\.venv\Scripts\python.exe toggle_hospitality_break.py restore   # right after
"""
import asyncio
import sys
import uuid

TENANT_ID = uuid.UUID("e1ee4d0e-e8d7-4d5d-9778-c8954687e63f")
REAL_CODE = "4010"
BROKEN_CODE = "9999-DOES-NOT-EXIST"


async def main(mode: str) -> None:
    from sqlalchemy import select

    from app.core.db.database import tenant_session
    from app.modules.cases.models.core import CaseType

    async with tenant_session(TENANT_ID) as session:
        result = await session.execute(
            select(CaseType).where(CaseType.plugin_key == "hospitality")
        )
        case_types = result.scalars().all()
        if not case_types:
            print("No hospitality CaseType found — nothing to do.")
            return

        for ct in case_types:
            meta = dict(ct.meta or {})
            before = meta.get("revenue_gl_account")
            meta["revenue_gl_account"] = BROKEN_CODE if mode == "break" else REAL_CODE
            ct.meta = meta
            session.add(ct)
            print(f"CaseType id={ct.id} code={ct.code}: revenue_gl_account {before!r} -> {meta['revenue_gl_account']!r}")

        await session.commit()
        print(f"Done ({mode}).")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("break", "restore"):
        print("Usage: python toggle_hospitality_break.py [break|restore]")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
