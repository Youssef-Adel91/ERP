"""
app/core/sequences/service.py — Gapless Document Number Allocator

IMPORTANT: This function must be called INSIDE an open transaction that the caller
controls. It issues SELECT ... FOR UPDATE which serializes concurrent writers at the
database level — guaranteeing zero gaps and zero duplicates even under high concurrency.

DO NOT commit inside this function. The caller's commit atomically persists the
incremented counter alongside the document being created, preventing partial writes.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sequences.models import DocumentSequence

logger = logging.getLogger(__name__)


async def allocate_sequence(
    session: AsyncSession,
    doc_type: str,
    fiscal_year: int,
    branch_id: UUID | None = None,
    prefix: str | None = None,
    padding: int = 6,
) -> tuple[str, int]:
    """
    Atomically allocate the next sequence number for a given document type.

    Returns:
        (formatted_number, raw_integer)
        e.g. ("INV-000042", 42)

    This function participates in the caller's transaction — do NOT commit inside.
    """
    # SELECT ... FOR UPDATE serializes concurrent writers on this specific row.
    # Any other transaction attempting to read the same row will block until
    # the current transaction commits or rolls back.
    stmt = (
        select(DocumentSequence)
        .where(
            DocumentSequence.doc_type == doc_type,
            DocumentSequence.branch_id == branch_id,
            DocumentSequence.fiscal_year == fiscal_year,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    seq = result.scalars().first()

    if seq is None:
        # First document of this type/branch/year — create the counter row.
        seq = DocumentSequence(
            doc_type=doc_type,
            branch_id=branch_id,
            fiscal_year=fiscal_year,
            prefix=prefix or "",
            padding=padding,
            next_value=1,
        )
        session.add(seq)
        await session.flush()  # Obtain an ID and lock the new row

        # Re-acquire with FOR UPDATE after insert
        stmt2 = (
            select(DocumentSequence)
            .where(DocumentSequence.id == seq.id)
            .with_for_update()
        )
        result2 = await session.execute(stmt2)
        seq = result2.scalars().first()

    raw_value = seq.next_value
    seq.next_value = raw_value + 1
    # Flush so the incremented value is visible within this transaction,
    # but do NOT commit — caller decides when to commit.
    await session.flush()

    effective_prefix = prefix if prefix is not None else seq.prefix
    formatted = f"{effective_prefix}{str(raw_value).zfill(seq.padding)}"
    logger.debug("Allocated %s sequence #%d → %s", doc_type, raw_value, formatted)
    return formatted, raw_value
