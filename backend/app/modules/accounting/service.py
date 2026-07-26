"""
app/modules/accounting/service.py — Accounting Business Logic

All functions accept an AsyncSession that has already had its search_path
set by the get_tenant_db dependency. No raw SQL schema references needed.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sequences.service import allocate_sequence
from app.modules.accounting.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalEntryStatus,
    TransactionLine,
)
from app.modules.accounting.schemas import (
    AccountBalanceResponse,
    AccountCreateRequest,
    JournalEntryCreateRequest,
)

logger = logging.getLogger(__name__)


# ── Custom Exceptions ─────────────────────────────────────────────────────────


class UnbalancedEntryError(ValueError):
    """Σ debits ≠ Σ credits — raised before any DB write."""


class PostedEntryMutationError(PermissionError):
    """Attempt to modify or re-post an already POSTED journal entry."""


class AccountNotFoundError(LookupError):
    """Referenced account code does not exist in this tenant's Chart of Accounts."""


# ── Accounts ──────────────────────────────────────────────────────────────────


async def get_accounts(
    db: AsyncSession,
    account_type: AccountType | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Account]:
    filters = []
    if account_type:
        filters.append(Account.account_type == account_type)
    result = await db.execute(
        select(Account)
        .where(*filters, Account.is_active.is_(True))
        .order_by(Account.code)
        .limit(limit)
        .offset(offset),
    )
    return list(result.scalars().all())


async def create_account(data: AccountCreateRequest, db: AsyncSession) -> Account:
    existing = await db.execute(select(Account).where(Account.code == data.code))
    if existing.scalar_one_or_none():
        raise ValueError(f"Account code '{data.code}' already exists.")

    account = Account(
        code=data.code,
        name=data.name,
        name_ar=data.name_ar,
        account_type=data.account_type,
        is_system=data.is_system,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def get_account_balance(
    account_code: str,
    db: AsyncSession,
) -> AccountBalanceResponse:
    """
    Compute the running balance for an account from all POSTED entries.

    Balance interpretation by account type:
      Asset / Expense   → debit - credit  (positive = debit balance)
      Liability / Equity / Revenue → credit - debit (positive = credit balance)
    """
    # Fetch account metadata
    acct_result = await db.execute(
        select(Account).where(Account.code == account_code),
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise AccountNotFoundError(f"Account '{account_code}' not found.")

    # Aggregate debits and credits from POSTED entries only
    balance_result = await db.execute(
        select(
            func.coalesce(func.sum(TransactionLine.debit), Decimal("0")),
            func.coalesce(func.sum(TransactionLine.credit), Decimal("0")),
        )
        .join(JournalEntry, TransactionLine.journal_entry_id == JournalEntry.id)
        .where(
            TransactionLine.account_code == account_code,
            JournalEntry.status == JournalEntryStatus.POSTED,
        ),
    )
    total_debit, total_credit = balance_result.one()

    # Normal balance direction
    if account.account_type in (AccountType.ASSET, AccountType.EXPENSE):
        balance = total_debit - total_credit
    else:
        balance = total_credit - total_debit

    return AccountBalanceResponse(
        account_code=account.code,
        account_name=account.name,
        account_type=account.account_type,
        total_debit=total_debit,
        total_credit=total_credit,
        balance=balance,
    )


# ── Journal Entries ───────────────────────────────────────────────────────────


async def get_journal_entries(
    db: AsyncSession,
    status_filter: JournalEntryStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[JournalEntry]:
    filters = []
    if status_filter:
        filters.append(JournalEntry.status == status_filter)
    result = await db.execute(
        select(JournalEntry)
        .where(*filters)
        .order_by(JournalEntry.created_at.desc())
        .limit(limit)
        .offset(offset),
    )
    return list(result.scalars().all())


async def create_draft_journal_entry(
    data: JournalEntryCreateRequest,
    created_by: UUID,
    db: AsyncSession,
) -> JournalEntry:
    """
    Validate balance and insert a DRAFT journal entry with all its lines.

    Double-entry is checked here (service layer) as a second safety net
    after the Pydantic validator. Neither check hits the DB.
    """
    total_debit = sum(line.debit for line in data.lines)
    total_credit = sum(line.credit for line in data.lines)

    if total_debit.quantize(Decimal("0.0001")) != total_credit.quantize(Decimal("0.0001")):
        raise UnbalancedEntryError(
            f"Unbalanced entry: Σdebits={total_debit} ≠ Σcredits={total_credit} "
            f"(Δ={abs(total_debit - total_credit)})",
        )

    entry = JournalEntry(
        reference=data.reference,
        description=data.description,
        status=JournalEntryStatus.DRAFT,
        created_by=created_by,
    )
    db.add(entry)
    await db.flush()  # Get entry.id for FK in TransactionLine

    for line_data in data.lines:
        # Fetch account name for snapshot (optional — graceful fallback)
        acct_result = await db.execute(
            select(Account.name).where(Account.code == line_data.account_code),
        )
        account_name = acct_result.scalar_one_or_none() or line_data.account_code

        line = TransactionLine(
            journal_entry_id=entry.id,
            account_code=line_data.account_code,
            account_name=account_name,
            debit=line_data.debit,
            credit=line_data.credit,
            description=line_data.description,
        )
        db.add(line)

    await db.commit()
    await db.refresh(entry)
    logger.info("Created DRAFT journal entry '%s' (id=%s)", entry.reference, entry.id)
    return entry


async def post_journal_entry(
    entry_id: UUID,
    posted_by: UUID,
    db: AsyncSession,
) -> JournalEntry:
    """
    Transition a DRAFT entry to POSTED (immutable).

    Once POSTED, a journal entry cannot be modified or deleted.
    To correct it, create a reversing entry (create_reversing_entry).
    """
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id),
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise LookupError(f"Journal entry '{entry_id}' not found.")
    if entry.status == JournalEntryStatus.POSTED:
        raise PostedEntryMutationError(
            f"Journal entry '{entry_id}' is already POSTED and immutable.",
        )
    if entry.status == JournalEntryStatus.VOID:
        raise PostedEntryMutationError(
            f"Journal entry '{entry_id}' is VOID and cannot be posted.",
        )

    entry.status = JournalEntryStatus.POSTED
    entry.posted_at = datetime.now(UTC).replace(tzinfo=None)

    # 1. Allocate gapless sequence number (SELECT FOR UPDATE inside this transaction)
    fiscal_year = (entry.posted_at or datetime.now(UTC)).year
    _seq_str, seq_no = await allocate_sequence(
        session=db,
        doc_type="journal_entry",
        fiscal_year=fiscal_year,
        branch_id=entry.branch_id,
        prefix="JE-",
        padding=6,
    )
    entry.sequence_no = seq_no

    # 2. Compute hash chain (SELECT FOR UPDATE on chain tip, also inside this tx)
    from app.modules.accounting.services.hash import compute_entry_hash
    lines = list(entry.lines)  # already loaded via selectin
    prev_hash, entry_hash = await compute_entry_hash(db, entry, lines)
    entry.prev_hash = prev_hash
    entry.entry_hash = entry_hash

    await db.commit()
    await db.refresh(entry)
    logger.info("Posted journal entry '%s' (id=%s) seq#%d", entry.reference, entry.id, seq_no)
    return entry


async def create_reversing_entry(
    original_entry_id: UUID,
    created_by: UUID,
    db: AsyncSession,
) -> JournalEntry:
    """
    Create a reversing journal entry by swapping all debits and credits.
    The original entry must be POSTED. The reversing entry is created as DRAFT.
    """
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == original_entry_id),
    )
    original = result.scalar_one_or_none()

    if not original:
        raise LookupError(f"Journal entry '{original_entry_id}' not found.")
    if original.status != JournalEntryStatus.POSTED:
        raise ValueError("Only POSTED entries can be reversed.")

    reversing = JournalEntry(
        reference=f"REV-{original.reference}",
        description=f"Reversal of: {original.description}",
        status=JournalEntryStatus.DRAFT,
        source_type="reversal",
        source_id=original.id,
        created_by=created_by,
    )
    db.add(reversing)
    await db.flush()

    for line in original.lines:
        db.add(TransactionLine(
            journal_entry_id=reversing.id,
            account_code=line.account_code,
            account_name=line.account_name,
            debit=line.credit,    # Swap debit ↔ credit
            credit=line.debit,    # Swap debit ↔ credit
            description=f"[REVERSAL] {line.description or ''}".strip(),
        ))

    await db.commit()
    await db.refresh(reversing)
    logger.info("Created reversing entry '%s' for '%s'", reversing.reference, original.reference)
    return reversing
