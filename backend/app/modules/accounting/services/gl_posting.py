"""
app/modules/accounting/services/gl_posting.py — The single gate for GL posting

Every automated journal entry must pass through `reserve_posting()` first. The
contract is deliberately narrow:

    reserved = await reserve_posting(session, source_type="case", source_id=...,
                                     entry_kind="hospitality_checkout_revenue", ...)
    if not reserved:
        return                      # already posted (or in flight) — idempotent no-op
    entry = await create_journal_entry(session=session, ...)   # same transaction
    await mark_posted(session, posting_id=..., journal_entry_id=entry.id)

WHY RESERVE BEFORE POSTING (not after)
---------------------------------------
The gl_postings row is the claim. Writing it first, in the SAME transaction as
the journal entry, means a crash between the two can only ever lose BOTH (the
transaction rolls back) — never leave a journal entry that no claim points at.
Posting first and claiming after would reintroduce orphan entries through a
different door.

WHY ON CONFLICT DO NOTHING (not a bare INSERT)
-----------------------------------------------
Postgres rejecting a duplicate with an IntegrityError would turn today's
"silent duplicate" into "500 on a legitimate retry" — a different bug, not a
fix. A collision here means "somebody already claimed this exact posting",
which is a SUCCESS from the caller's point of view: there is nothing left to
do. So the insert is conflict-tolerant and the function simply returns False.

RETRYING A FAILED POSTING
--------------------------
A row left in FAILED state is a real failure that a human may want retried.
`reserve_posting(..., retry_failed=True)` flips that row back to RESERVED and
returns it, so a retry path can exist without deleting history (attempts is
incremented, the previous error is kept until it succeeds).
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models.posting import GLPosting, GLPostingStatus

logger = logging.getLogger(__name__)


async def reserve_posting(
    session: AsyncSession,
    *,
    source_type: str,
    source_id: uuid.UUID | str,
    entry_kind: str,
    invoice_number: str | None = None,
    amount: Decimal | float | None = None,
    currency: str = "EGP",
    retry_failed: bool = False,
) -> GLPosting | None:
    """Claim the right to post (source_type, source_id, entry_kind).

    Returns the GLPosting row when the claim is ours to act on, or None when
    this exact posting is already claimed — in which case the caller must do
    nothing at all. None is a normal, expected outcome, not an error.
    """
    if isinstance(source_id, str):
        source_id = uuid.UUID(source_id)

    values = {
        "id": uuid.uuid4(),
        "source_type": source_type,
        "source_id": source_id,
        "entry_kind": entry_kind,
        "status": GLPostingStatus.RESERVED,
        "invoice_number": invoice_number,
        "amount": Decimal(str(amount)) if amount is not None else None,
        "currency": currency,
        "attempts": 1,
    }

    stmt = (
        pg_insert(GLPosting.__table__)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_gl_postings_source_kind")
        .returning(GLPosting.__table__.c.id)
    )
    result = await session.execute(stmt)
    inserted_id = result.scalar_one_or_none()

    if inserted_id is not None:
        await session.flush()
        return await session.get(GLPosting, inserted_id)

    # Someone already holds this claim. Look at what state it is in.
    existing = (
        await session.execute(
            select(GLPosting).where(
                GLPosting.source_type == source_type,
                GLPosting.source_id == source_id,
                GLPosting.entry_kind == entry_kind,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        # Extremely unlikely: conflict reported but row not visible. Treat as
        # claimed rather than racing to insert again.
        logger.warning(
            "GL posting conflict for %s/%s/%s but no row found — treating as claimed.",
            source_type, source_id, entry_kind,
        )
        return None

    if existing.status == GLPostingStatus.FAILED and retry_failed:
        existing.status = GLPostingStatus.RESERVED
        existing.attempts = (existing.attempts or 0) + 1
        session.add(existing)
        await session.flush()
        return existing

    logger.info(
        "GL posting already claimed (%s) for %s/%s/%s — skipping, nothing to do.",
        existing.status.value if hasattr(existing.status, "value") else existing.status,
        source_type, source_id, entry_kind,
    )
    return None


async def mark_posted(
    session: AsyncSession,
    *,
    posting_id: uuid.UUID,
    journal_entry_id: uuid.UUID,
) -> None:
    """Confirm a reservation once its journal entry exists."""
    await session.execute(
        update(GLPosting.__table__)
        .where(GLPosting.__table__.c.id == posting_id)
        .values(
            status=GLPostingStatus.POSTED,
            journal_entry_id=journal_entry_id,
            error_type=None,
            error_message=None,
        )
    )


async def mark_failed(
    session: AsyncSession,
    *,
    posting_id: uuid.UUID,
    exc: BaseException,
) -> None:
    """Record why a reserved posting did not become a journal entry.

    Kept deliberately separate from the failing transaction: the caller is
    expected to run this on a session that is still usable (see
    handle_invoice_created, which opens a fresh one after a rollback).
    """
    await session.execute(
        update(GLPosting.__table__)
        .where(GLPosting.__table__.c.id == posting_id)
        .values(
            status=GLPostingStatus.FAILED,
            error_type=type(exc).__name__,
            error_message=str(exc)[:2000],
        )
    )


async def get_posting_status(
    session: AsyncSession,
    *,
    source_type: str,
    source_id: uuid.UUID | str,
    entry_kind: str,
) -> GLPosting | None:
    """Read the posting record for one source+kind, or None if never attempted.

    This is what plugin listeners should consult instead of the old
    `case.data["gl_*_posted"]` booleans.
    """
    if isinstance(source_id, str):
        source_id = uuid.UUID(source_id)
    return (
        await session.execute(
            select(GLPosting).where(
                GLPosting.source_type == source_type,
                GLPosting.source_id == source_id,
                GLPosting.entry_kind == entry_kind,
            )
        )
    ).scalar_one_or_none()
