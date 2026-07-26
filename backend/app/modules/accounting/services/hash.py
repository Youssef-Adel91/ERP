"""
app/modules/accounting/services/hash.py — Hash-Chained Journal Entry Security

Each posted journal entry carries:
  - prev_hash: the sha256 of the PREVIOUS entry in the chain (or "GENESIS_HASH")
  - entry_hash: sha256(prev_hash + canonical_payload)

This creates an unbreakable chain: tampering with ANY entry invalidates every
subsequent hash, making ledger manipulation cryptographically detectable.

CONCURRENCY NOTE:
    We use .with_for_update() when fetching the chain tip. This serializes
    concurrent postings to the SAME period, preventing two entries from both
    claiming the same prev_hash and branching the chain.
"""
from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import JournalEntry, TransactionLine

logger = logging.getLogger(__name__)

GENESIS_HASH = "GENESIS_HASH"


def _canonical_payload(entry: JournalEntry, lines: list[TransactionLine]) -> str:
    """
    Produce a deterministic, canonical JSON string for hashing.

    Rules:
    - All fields are sorted by key
    - Amounts serialised as strings (avoid float precision issues)
    - Lines sorted by account_code then by debit/credit for full determinism
    """
    line_data = sorted(
        [
            {
                "account_code": line.account_code,
                "debit": str(line.debit),
                "credit": str(line.credit),
            }
            for line in lines
        ],
        key=lambda x: (x["account_code"], x["debit"], x["credit"]),
    )

    payload = {
        "reference": entry.reference,
        "posted_at": entry.posted_at.isoformat() if entry.posted_at else "",
        "lines": line_data,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


async def compute_entry_hash(
    session: AsyncSession,
    entry: JournalEntry,
    lines: list[TransactionLine],
) -> tuple[str, str]:
    """
    Compute (prev_hash, entry_hash) for a journal entry being posted.

    Must be called inside an open transaction with FOR UPDATE to serialize
    concurrent postings. The caller must flush/commit after receiving results
    and writing them back to the entry.

    Args:
        session:  The active AsyncSession (inside caller's transaction)
        entry:    The JournalEntry being posted (not yet committed)
        lines:    The TransactionLines belonging to this entry

    Returns:
        (prev_hash, entry_hash) — both are hex sha256 strings (or GENESIS_HASH for prev)
    """
    # Fetch the most recently posted entry by sequence_no to get the chain tip.
    # FOR UPDATE serializes concurrent postings so two entries cannot share a prev_hash.
    stmt = (
        select(JournalEntry)
        .where(
            JournalEntry.status == "posted",
            JournalEntry.entry_hash.is_not(None),
            JournalEntry.id != entry.id,
        )
        .order_by(JournalEntry.sequence_no.desc())
        .limit(1)
        .with_for_update()
    )
    result = await session.execute(stmt)
    previous_entry = result.scalars().first()

    if previous_entry is None or previous_entry.entry_hash is None:
        prev_hash = GENESIS_HASH
        logger.info("Hash chain: No prior entry found — starting from GENESIS_HASH")
    else:
        prev_hash = previous_entry.entry_hash
        logger.debug(
            "Hash chain: chaining off entry seq#%s (hash=%s…)",
            previous_entry.sequence_no,
            prev_hash[:16],
        )

    canonical = _canonical_payload(entry, lines)
    raw = (prev_hash + canonical).encode("utf-8")
    entry_hash = hashlib.sha256(raw).hexdigest()

    return prev_hash, entry_hash


async def verify_hash_chain(session: AsyncSession) -> tuple[bool, int | None]:
    """
    Validate the integrity of the entire hash chain for the current tenant.

    Returns:
        (is_valid, first_broken_sequence_no)
        If valid: (True, None)
        If broken: (False, sequence_no of first tampered entry)
    """
    stmt = (
        select(JournalEntry)
        .where(
            JournalEntry.status == "posted",
            JournalEntry.entry_hash.is_not(None),
        )
        .order_by(JournalEntry.sequence_no.asc())
    )
    result = await session.execute(stmt)
    entries = result.scalars().all()

    prev_hash = GENESIS_HASH
    for entry in entries:
        # Re-fetch lines for this entry
        lines_stmt = (
            select(TransactionLine)
            .where(TransactionLine.journal_entry_id == entry.id)
        )
        lines_result = await session.execute(lines_stmt)
        lines = list(lines_result.scalars().all())

        canonical = _canonical_payload(entry, lines)
        expected_hash = hashlib.sha256((prev_hash + canonical).encode()).hexdigest()

        if entry.entry_hash != expected_hash:
            logger.error(
                "HASH CHAIN BROKEN at sequence_no=%s! Expected %s, got %s",
                entry.sequence_no,
                expected_hash[:16],
                entry.entry_hash[:16] if entry.entry_hash else "None",
            )
            return False, entry.sequence_no

        prev_hash = entry.entry_hash

    return True, None
