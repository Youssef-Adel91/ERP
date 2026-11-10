"""
verify_item4_closed_period_rejection.py — P1 Item 4 live enforcement proof.

Proves the manual DRAFT->POST journal-entry path (post_journal_entry() in
app/modules/accounting/service.py) now rejects a posting dated inside a
CLOSED period, and that reopening the period lets the identical posting
succeed afterwards. This is the path I added period enforcement to this
segment (the event-driven create_journal_entry() path already had it
before this segment, per the code review at the start of Item 4).

Calls the REAL service functions directly against the tenant DB --
create_draft_journal_entry, post_journal_entry, close_period,
reopen_period -- the exact same functions the API router calls. This is a
live run of the actual enforcement code, not a reimplementation of it.

One deliberate test-setup step: create_draft_journal_entry() does not
accept an entry_date argument -- JournalEntry.entry_date defaults to
date.today() at the ORM layer (see models/core.py) and there is no field
on JournalEntryCreateRequest to override it. So after creating the draft
(which lands on today's date), this script does a direct, explicit
UPDATE of that one just-created test row's entry_date to 2024-06-15
before calling post_journal_entry() -- this is test-fixture setup for a
throwaway entry created by this script, not a mutation of any real
business data.

Steps:
  0. Find which tenant schema owns period id
     3369ee21-c53c-4597-8993-277c0a89618f (the 2024-06 period an OWNER
     just closed live via the accounting UI).
  1. Create a DRAFT journal entry, force its entry_date to 2024-06-15,
     attempt to POST it -- EXPECT ClosedPeriodError.
  2. Reopen the period -- EXPECT is_closed -> False.
  3. POST the same draft again -- EXPECT success.
  4. Re-close the period, restoring the state the OWNER left it in via
     the UI, so this script doesn't quietly leave a period reopened that
     a human closed on purpose a few minutes ago.

Usage (from backend/, same venv as the other verify_*.py scripts):
    python verify_item4_closed_period_rejection.py
"""
import asyncio
import os
import uuid
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = os.environ["DATABASE_URL"]
TARGET_PERIOD_ID = "3369ee21-c53c-4597-8993-277c0a89618f"


async def find_tenant_schema(engine) -> str | None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%' ORDER BY schema_name")
        )
        schemas = [row[0] for row in result.all()]

    async with engine.connect() as conn:
        for schema in schemas:
            has_table = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = :schema AND table_name = 'accounting_periods'"
                    ),
                    {"schema": schema},
                )
            ).scalar()
            if not has_table:
                continue
            found = (
                await conn.execute(
                    text(f'SELECT 1 FROM "{schema}".accounting_periods WHERE id = :id'),
                    {"id": TARGET_PERIOD_ID},
                )
            ).scalar()
            if found:
                return schema
    return None


async def main():
    engine = create_async_engine(DATABASE_URL, future=True)
    schema = await find_tenant_schema(engine)
    if not schema:
        print(f"Could not find a tenant owning period {TARGET_PERIOD_ID}. Aborting.")
        await engine.dispose()
        return
    print(f"Target tenant schema: {schema}\n")

    from sqlalchemy import update

    from app.modules.accounting.service import (
        create_draft_journal_entry,
        post_journal_entry,
        close_period,
        reopen_period,
    )
    from app.modules.accounting.services.journal import ClosedPeriodError
    from app.modules.accounting.schemas import JournalEntryCreateRequest, TransactionLineCreateRequest
    from app.modules.accounting.models import JournalEntry

    # This codebase deliberately does NOT use `SET search_path` for tenant
    # routing (it's unsafe under PgBouncer transaction pooling -- see
    # app/core/db/base.py's own docstring). Models declare the SYMBOLIC
    # schema "tenant" in __table_args__, and the real per-tenant schema is
    # substituted at SQL-compile time via schema_translate_map, bound at
    # the ENGINE level (see tenant_session() in app/core/db/database.py).
    # Mirroring that exact mechanism here rather than SET search_path.
    translated_engine = engine.execution_options(schema_translate_map={"tenant": schema})
    Session = async_sessionmaker(translated_engine, expire_on_commit=False, class_=AsyncSession)
    test_user_id = uuid.uuid4()

    async with Session() as db:

        entry_req = JournalEntryCreateRequest(
            reference=f"P1-ITEM4-CLOSEDTEST-{uuid.uuid4().hex[:8]}",
            description="P1 Item 4 live test: posting into a CLOSED period must be rejected",
            lines=[
                TransactionLineCreateRequest(account_code="1200", debit=100, credit=0, description="test debit"),
                TransactionLineCreateRequest(account_code="4010", debit=0, credit=100, description="test credit"),
            ],
        )

        print("=" * 70)
        print("SETUP: create DRAFT entry, force entry_date to 2024-06-15")
        print("       (period 2024-06 was just closed live via the accounting UI)")
        print("=" * 70)
        draft = await create_draft_journal_entry(entry_req, test_user_id, db)
        print(f"  draft created: id={draft.id} status={draft.status} entry_date(pre-force)={draft.entry_date}")

        # Set the attribute on the already-loaded ORM object and commit
        # through the ORM (NOT a bulk Core UPDATE statement). A bulk
        # `db.execute(update(JournalEntry)...)` writes the row correctly
        # but does NOT refresh/expire the `draft` Python object already
        # sitting in this Session's identity map -- so a later
        # `select(JournalEntry).where(id==draft.id)` inside
        # post_journal_entry() would return that SAME stale in-memory
        # object (still showing today's date) instead of a freshly read
        # row. Assigning the attribute directly keeps the identity map
        # correct, the same way any normal ORM write in this app does.
        draft.entry_date = date(2024, 6, 15)
        db.add(draft)
        await db.commit()
        # NOTE: deliberately NOT calling db.refresh(draft) here. With
        # expire_on_commit=False, draft.entry_date already reflects what we
        # just set in Python -- no refresh needed. A refresh() call was
        # tried here originally and caused a *different*, self-inflicted
        # bug: it expires ALL of the object's loaded state, including the
        # lazy="selectin" `.lines` relationship, and when post_journal_entry()
        # later touches entry.lines on this same cached object, SQLAlchemy
        # attempts an on-demand lazy reload that isn't safely awaitable in
        # this context -> "MissingGreenlet". Confirmed live: removing this
        # refresh() call was the fix.
        print(f"  entry_date forced to 2024-06-15 (test fixture setup for this throwaway entry): now={draft.entry_date}")

        print()
        print("=" * 70)
        print("STEP 1: attempt to POST the entry dated inside the CLOSED period")
        print("=" * 70)
        try:
            await post_journal_entry(draft.id, test_user_id, db)
            print("  UNEXPECTED: post_journal_entry() succeeded -- period enforcement DID NOT block it!")
        except ClosedPeriodError as e:
            print(f"  EXPECTED REJECTION -- ClosedPeriodError raised:")
            print(f"    {e}")
            # Deliberately NOT calling db.rollback() here. ClosedPeriodError
            # is raised purely from a Python-level check in
            # post_journal_entry() BEFORE any row is modified (entry.status
            # is only set to POSTED after that check passes) -- no SQL
            # statement failed and no transaction was aborted, so there is
            # nothing to roll back. A rollback() here was tried and is what
            # caused STEP 3's MissingGreenlet: SQLAlchemy's rollback()
            # unconditionally EXPIRES every loaded object regardless of
            # expire_on_commit, so the next access to `draft.id` (passed
            # into post_journal_entry() in STEP 3) triggered an implicit
            # synchronous reload of the expired attribute -- unsupported on
            # an AsyncSession. Confirmed live via full traceback.
        except Exception as e:
            print(f"  UNEXPECTED exception type {type(e).__name__}: {e}")
            await db.rollback()

        print()
        print("=" * 70)
        print("STEP 2: reopen the period (OWNER action)")
        print("=" * 70)
        period = await reopen_period(uuid.UUID(TARGET_PERIOD_ID), db)
        print(f"  period {period.name}: is_closed={period.is_closed} closed_by={period.closed_by} closed_at={period.closed_at}")

        print()
        print("=" * 70)
        print("STEP 3: attempt to POST the same draft again -- should now succeed")
        print("=" * 70)
        try:
            posted = await post_journal_entry(draft.id, test_user_id, db)
            print(f"  SUCCESS: entry {posted.id} status={posted.status} posted_at={posted.posted_at}")
        except Exception as e:
            print(f"  UNEXPECTED FAILURE: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # A DBAPI-level failure (e.g. an aborted Postgres transaction)
            # leaves this connection unusable for any further statement
            # until rolled back -- without this, STEP 4 below would fail
            # too, with a confusing secondary "transaction aborted" error
            # that has nothing to do with period enforcement.
            await db.rollback()

        print()
        print("=" * 70)
        print("STEP 4: re-close the period to restore the state the OWNER set via the UI")
        print("=" * 70)
        period = await close_period(uuid.UUID(TARGET_PERIOD_ID), test_user_id, db)
        print(f"  period {period.name}: is_closed={period.is_closed}")

    await engine.dispose()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
