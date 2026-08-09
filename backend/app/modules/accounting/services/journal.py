"""
app/modules/accounting/services/journal.py — Double-Entry Journal Engine Service

Implements the Golden Rule of Accounting:
Before saving a JournalEntry, the service MUST mathematically assert that
SUM(debits) == SUM(credits) to the 4th decimal place (0.0001).
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models.core import (
    Account,
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
)

logger = logging.getLogger(__name__)

FOUR_DECIMALS = Decimal("0.0001")


class UnbalancedJournalEntryError(ValueError):
    """Raised when SUM(debits) != SUM(credits) in a journal entry."""


class ClosedPeriodError(ValueError):
    """Raised when attempting to post a journal entry into a closed or undefined accounting period."""


# Compatibility alias for existing tests/code
UnbalancedEntryError = UnbalancedJournalEntryError


async def create_journal_entry(
    session: AsyncSession,
    description: str,
    entry_date: date | None = None,
    lines_data: list[Any] | None = None,
    reference_id: UUID | None = None,
    **kwargs: Any,
) -> JournalEntry:
    """
    Create and persist a Double-Entry Journal Entry after strictly asserting
    SUM(debits) == SUM(credits).
    
    Accepts lines_data as a list of dicts, Pydantic schemas, or object instances.
    """
    if entry_date is None:
        entry_date = date.today()
    if lines_data is None:
        lines_data = kwargs.pop("lines", None)
    if not lines_data:
        raise ValueError("A journal entry must contain at least one debit and one credit line.")

    # ── PERIOD VALIDATION (THE HARD BLOCK) ────────────────────────────────────
    from datetime import datetime, time
    from app.modules.accounting.models.core import AccountingPeriod
    entry_start_dt = datetime.combine(entry_date, time.min)
    entry_end_dt = datetime.combine(entry_date, time.max)
    period_stmt = select(AccountingPeriod).where(
        AccountingPeriod.start_date <= entry_end_dt,
        AccountingPeriod.end_date >= entry_start_dt,
    )
    period_res = await session.execute(period_stmt)
    period = period_res.scalars().first()

    if period is None:
        raise ClosedPeriodError(
            f"No accounting period defined for entry date '{entry_date}'. Cannot post journal entry."
        )
    if period.is_closed:
        raise ClosedPeriodError(
            f"Accounting period '{period.name}' ({period.start_date.date()} to {period.end_date.date()}) is CLOSED. Cannot post journal entry."
        )

    parsed_lines = []

    total_debits = Decimal("0.0000")
    total_credits = Decimal("0.0000")

    for line in lines_data:
        # Support dicts, Pydantic schemas, or arbitrary objects
        def _get(key: str, default: Any = None) -> Any:
            if isinstance(line, dict):
                return line.get(key, default)
            return getattr(line, key, default)

        raw_debit = _get("debit", Decimal("0"))
        raw_credit = _get("credit", Decimal("0"))

        debit_val = Decimal(str(raw_debit)).quantize(FOUR_DECIMALS)
        credit_val = Decimal(str(raw_credit)).quantize(FOUR_DECIMALS)

        if debit_val < 0 or credit_val < 0:
            raise ValueError("Debit and credit amounts cannot be negative.")
        if debit_val > 0 and credit_val > 0:
            raise ValueError("A journal line cannot have both debit and credit amounts greater than zero.")
        if debit_val == 0 and credit_val == 0:
            raise ValueError("A journal line must have either a non-zero debit or credit amount.")

        total_debits += debit_val
        total_credits += credit_val

        parsed_lines.append({
            "account_id": _get("account_id"),
            "account_code": _get("account_code"),
            "account_name": _get("account_name"),
            "debit": debit_val,
            "credit": credit_val,
            "description": _get("description"),
            "branch_id": _get("branch_id"),
            "cost_center_id": _get("cost_center_id"),
            "contact_id": _get("contact_id"),
            "currency": _get("currency", "EGP"),
            "base_amount": _get("base_amount", max(debit_val, credit_val)),
        })

    # ── THE GOLDEN RULE OF ACCOUNTING ─────────────────────────────────────────
    if total_debits != total_credits:
        raise UnbalancedJournalEntryError(
            f"Unbalanced journal entry: SUM(debits)={total_debits} != "
            f"SUM(credits)={total_credits} (difference: {abs(total_debits - total_credits)})"
        )

    # ── Resolve Account ID / Code / Name ──────────────────────────────────────
    for pl in parsed_lines:
        account_id = pl["account_id"]
        account_code = pl["account_code"]

        if account_id and not account_code:
            acct_res = await session.execute(select(Account).where(Account.id == account_id))
            acct = acct_res.scalar_one_or_none()
            if not acct:
                raise LookupError(f"Account with id '{account_id}' not found.")
            pl["account_code"] = acct.code
            if not pl["account_name"]:
                pl["account_name"] = acct.name
        elif account_code and not account_id:
            acct_res = await session.execute(select(Account).where(Account.code == account_code))
            acct = acct_res.scalar_one_or_none()
            if not acct:
                raise LookupError(f"Account with code '{account_code}' not found.")
            pl["account_id"] = acct.id
            if not pl["account_name"]:
                pl["account_name"] = acct.name
        elif not account_id and not account_code:
            raise ValueError("Each journal line must specify either 'account_id' or 'account_code'.")

    # ── Persist Entry & Lines ─────────────────────────────────────────────────
    status = kwargs.pop("status", JournalEntryStatus.DRAFT)
    reference = kwargs.pop("reference", None)
    if reference_id and not reference:
        reference = str(reference_id)

    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        reference_id=reference_id,
        reference=reference,
        status=status,
        **kwargs,
    )
    session.add(entry)
    await session.flush()  # Obtain entry.id

    for pl in parsed_lines:
        line_obj = JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=pl["account_id"],
            account_code=pl["account_code"],
            account_name=pl["account_name"] or "",
            debit=pl["debit"],
            credit=pl["credit"],
            description=pl["description"],
            branch_id=pl["branch_id"],
            cost_center_id=pl["cost_center_id"],
            contact_id=pl["contact_id"],
            currency=pl["currency"],
            base_amount=pl["base_amount"],
        )
        session.add(line_obj)

    await session.commit()
    await session.refresh(entry)
    logger.info("Created JournalEntry id=%s (reference_id=%s) total=%s", entry.id, entry.reference_id, total_debits)
    return entry
