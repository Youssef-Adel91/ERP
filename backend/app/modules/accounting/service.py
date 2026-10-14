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
    AccountingPeriod,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
    TransactionLine,
)
from app.modules.accounting.services.journal import (
    ClosedPeriodError,
    UnbalancedEntryError,
    UnbalancedJournalEntryError,
    create_journal_entry,
)
from app.modules.accounting.services.mappings import (
    AccountMappingKey,
    get_default_account,
    get_default_account_code,
    get_default_account_id,
    resolve_default_accounts,
)
from app.modules.accounting.reports.trial_balance import generate_trial_balance
from app.modules.accounting.schemas import (
    AccountBalanceResponse,
    AccountCreateRequest,
    JournalEntryCreateRequest,
)

logger = logging.getLogger(__name__)


# ── Custom Exceptions ─────────────────────────────────────────────────────────
# Re-exported from app.modules.accounting.services.journal:
# UnbalancedEntryError, UnbalancedJournalEntryError


class PostedEntryMutationError(PermissionError):
    """Attempt to modify or re-post an already POSTED journal entry."""


class AccountNotFoundError(LookupError):
    """Referenced account code does not exist in this tenant's Chart of Accounts."""


class PeriodNotFoundError(LookupError):
    """Referenced accounting period does not exist."""


class PeriodAlreadyClosedError(ValueError):
    """Attempt to close a period that is already CLOSED."""


class PeriodAlreadyOpenError(ValueError):
    """Attempt to reopen a period that is already OPEN."""


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

    # NOTE: the Account model's column is `account_type` (see
    # app/modules/accounting/models/core.py), not `type`. Passing `type=`
    # to the SQLModel constructor was silently accepted as an unrecognized
    # kwarg (the same footgun found in Resource(is_active=...) earlier
    # today) — account_type was left at its default (there is none; it's a
    # required NOT NULL column), causing a Postgres IntegrityError on every
    # single call to this endpoint. Discovered via live verification.
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
        # Fetch account id and name for snapshot
        acct_result = await db.execute(
            select(Account.id, Account.name).where(Account.code == line_data.account_code),
        )
        acct_row = acct_result.one_or_none()
        if not acct_row:
            raise AccountNotFoundError(f"Account code '{line_data.account_code}' not found.")
        acct_id, account_name = acct_row

        line = TransactionLine(
            journal_entry_id=entry.id,
            account_id=acct_id,
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

    # P1 Item 4 — incidental gap found while wiring period enforcement:
    # create_journal_entry() (services/journal.py) already hard-blocks a
    # CLOSED/undefined period for the automated invoice.created path, but
    # this manual DRAFT -> POSTED path (POST /journal-entries/{id}/post)
    # built its own JournalEntry directly in create_draft_journal_entry()
    # and never checked the period at all — a manual entry could be posted
    # straight into a period an OWNER just closed. Same check, same error
    # type, so the router's existing exception handling (added below) covers
    # both paths identically.
    from datetime import time as _time
    entry_start_dt = datetime.combine(entry.entry_date, _time.min)
    entry_end_dt = datetime.combine(entry.entry_date, _time.max)
    period_res = await db.execute(
        select(AccountingPeriod).where(
            AccountingPeriod.start_date <= entry_end_dt,
            AccountingPeriod.end_date >= entry_start_dt,
        )
    )
    period = period_res.scalars().first()
    if period is None:
        raise ClosedPeriodError(
            f"No accounting period defined for entry date '{entry.entry_date}'. Cannot post journal entry."
        )
    if period.is_closed:
        raise ClosedPeriodError(
            f"Accounting period '{period.name}' ({period.start_date.date()} to "
            f"{period.end_date.date()}) is CLOSED. Cannot post journal entry."
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

    # P1 Item 4 — second incidental discovery (self-reported, not part of
    # the period-enforcement work): `list(entry.lines)` assumed the
    # lazy="selectin" relationship was already eager-loaded, but if `entry`
    # came back from the session identity map with its relationship state
    # expired (e.g. after any db.rollback() in the same session — rollback
    # always expires every loaded object, regardless of expire_on_commit),
    # that assumption breaks: accessing `.lines` then triggers an implicit
    # lazy-load, and plain synchronous lazy-loading is not supported on an
    # AsyncSession — it raises MissingGreenlet. Found live while re-testing
    # Item 4's "reopen then post succeeds" step (posting the same draft a
    # second time in one session, after the first attempt was rolled back).
    # Fixed with an explicit awaited query instead of relying on implicit
    # eager-load state — the same pattern already used safely in
    # verify_hash_chain() in services/hash.py (fetches TransactionLine
    # rows explicitly rather than touching a relationship attribute).
    lines_result = await db.execute(
        select(TransactionLine).where(TransactionLine.journal_entry_id == entry.id)
    )
    lines = list(lines_result.scalars().all())
    prev_hash, entry_hash = await compute_entry_hash(db, entry, lines)
    entry.prev_hash = prev_hash
    entry.entry_hash = entry_hash

    await db.commit()
    await db.refresh(entry)
    logger.info("Posted journal entry '%s' (id=%s) seq#%d", entry.reference, entry.id, seq_no)
    return entry


async def list_periods(
    db: AsyncSession,
    limit: int = 500,
    offset: int = 0,
) -> list[AccountingPeriod]:
    """List accounting periods, most recent start_date first."""
    result = await db.execute(
        select(AccountingPeriod)
        .order_by(AccountingPeriod.start_date.desc())
        .limit(limit)
        .offset(offset),
    )
    return list(result.scalars().all())


async def close_period(period_id: UUID, closed_by: UUID, db: AsyncSession) -> AccountingPeriod:
    """
    Close an accounting period — P1 Item 4 decision: OWNER-only (enforced at
    the router layer via require_role), every period starts OPEN, no
    scheduled auto-close. Closing is a deliberate act, and — per the same
    decision — reversible via reopen_period() below, not a one-way lock.
    """
    period = await db.get(AccountingPeriod, period_id)
    if not period:
        raise PeriodNotFoundError(f"Accounting period '{period_id}' not found.")
    if period.is_closed:
        raise PeriodAlreadyClosedError(f"Accounting period '{period.name}' is already CLOSED.")

    period.is_closed = True
    period.closed_by = closed_by
    period.closed_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(period)
    await db.commit()
    await db.refresh(period)
    logger.info("Accounting period '%s' (id=%s) CLOSED by user %s", period.name, period.id, closed_by)
    return period


async def reopen_period(period_id: UUID, db: AsyncSession) -> AccountingPeriod:
    """
    Reopen a CLOSED accounting period — P1 Item 4 decision: this is an
    explicit, OWNER-only exception path for a genuine correction, not a
    routine action. closed_by is intentionally left as-is (audit trail of
    who last closed it); only closed_at is cleared.
    """
    period = await db.get(AccountingPeriod, period_id)
    if not period:
        raise PeriodNotFoundError(f"Accounting period '{period_id}' not found.")
    if not period.is_closed:
        raise PeriodAlreadyOpenError(f"Accounting period '{period.name}' is already OPEN.")

    period.is_closed = False
    period.closed_at = None
    db.add(period)
    await db.commit()
    await db.refresh(period)
    logger.info("Accounting period '%s' (id=%s) REOPENED", period.name, period.id)
    return period


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
            account_id=line.account_id,
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
