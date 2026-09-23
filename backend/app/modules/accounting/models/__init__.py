"""
app/modules/accounting/models/__init__.py — Accounting ORM Models Exports
"""

from app.modules.accounting.models.core import (
    Account,
    AccountingPeriod,
    AccountType,
    DEFAULT_ACCOUNTS,
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
    PeriodStatus,
)
from app.modules.accounting.models.posting import GLPosting, GLPostingStatus

# Backwards compatibility alias for V1 code/tests
TransactionLine = JournalEntryLine

__all__ = [
    "AccountType",
    "JournalEntryStatus",
    "PeriodStatus",
    "Account",
    "AccountingPeriod",
    "JournalEntry",
    "JournalEntryLine",
    "TransactionLine",
    "DEFAULT_ACCOUNTS",
    "GLPosting",
    "GLPostingStatus",
]

