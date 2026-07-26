"""
app/modules/accounting/models.py — Tenant-Schema Accounting ORM Models
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Index, Numeric, UniqueConstraint, text
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase

# ── Enumerations ──────────────────────────────────────────────────────────────

class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"

class JournalEntryStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    VOID = "void"


# ── Account (Chart of Accounts) ───────────────────────────────────────────────

class Account(TenantBase, table=True):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accounts_code"),
        Index("ix_accounts_type", "account_type"),
        {"schema": "tenant"},
    )

    code: str = Field(max_length=20, index=True)
    name: str = Field(max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    account_type: AccountType = Field(sa_column=Column(sa.Enum(AccountType, name='accounttype', schema='tenant'), nullable=False))
    
    parent_id: UUID | None = Field(default=None, foreign_key="tenant.accounts.id")
    is_control: bool = Field(default=False)
    is_active: bool = Field(default=True)
    is_system: bool = Field(default=False)

    transaction_lines: list["TransactionLine"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Account.code == foreign(TransactionLine.account_code)",
            "lazy": "select",
            "viewonly": True,
        },
    )


# ── Accounting Period ─────────────────────────────────────────────────────────

class AccountingPeriod(TenantBase, table=True):
    __tablename__ = "accounting_periods"
    __table_args__ = ({"schema": "tenant"},)
    
    name: str = Field(max_length=100)
    start_date: datetime
    end_date: datetime
    is_closed: bool = Field(default=False)


# ── Journal Entry ─────────────────────────────────────────────────────────────

class JournalEntry(TenantBase, table=True):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_status", "status"),
        Index("ix_journal_entries_created_at", "created_at"),
        {"schema": "tenant"},
    )

    reference: str = Field(max_length=100, index=True)
    description: str = Field(max_length=2000)
    status: JournalEntryStatus = Field(default=JournalEntryStatus.DRAFT, sa_column=Column(sa.Enum(JournalEntryStatus, name='journalentrystatus', schema='tenant'), default=JournalEntryStatus.DRAFT, nullable=False))

    source_type: str | None = Field(default=None, max_length=50)
    source_id: UUID | None = Field(default=None)
    source_event_id: UUID | None = Field(default=None)

    # V2 Enhancements
    branch_id: UUID | None = Field(default=None, index=True)
    entry_hash: str | None = Field(default=None, max_length=128)
    prev_hash: str | None = Field(default=None, max_length=128)

    # Gapless sequence number — populated by allocate_sequence() at post time.
    # Drives the hash chain ordering (DESC query on sequence_no).
    sequence_no: int | None = Field(default=None, index=True)

    posted_at: datetime | None = Field(default=None)

    lines: list["TransactionLine"] = Relationship(
        back_populates="journal_entry",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


# ── Transaction Line ──────────────────────────────────────────────────────────

class TransactionLine(TenantBase, table=True):
    __tablename__ = "transaction_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit >= 0 AND credit >= 0) "
            "AND NOT (debit > 0 AND credit > 0) "
            "AND (debit > 0 OR credit > 0)",
            name="ck_transaction_lines_debit_xor_credit",
        ),
        {"schema": "tenant"},
    )

    journal_entry_id: UUID = Field(foreign_key="tenant.journal_entries.id", index=True)
    account_code: str = Field(max_length=20, index=True)
    account_name: str = Field(max_length=255, default="")

    debit: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )
    credit: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )

    # V2 enhancements
    branch_id: UUID | None = Field(default=None, index=True)
    cost_center_id: UUID | None = Field(default=None, index=True)
    contact_id: UUID | None = Field(default=None, index=True)
    currency: str = Field(default="EGP", max_length=3)
    base_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )

    description: str | None = Field(default=None, max_length=500)

    journal_entry: JournalEntry = Relationship(back_populates="lines")


# ── Default Chart of Accounts Seed ────────────────────────────────────────────

DEFAULT_ACCOUNTS: list[dict] = [
    {"code": "1100", "name": "Cash & Cash Equivalents", "account_type": AccountType.ASSET, "is_system": True},
    {"code": "1200", "name": "Accounts Receivable", "account_type": AccountType.ASSET, "is_system": True},
    {"code": "1300", "name": "Inventory", "account_type": AccountType.ASSET, "is_system": False},
    {"code": "2100", "name": "Accounts Payable", "account_type": AccountType.LIABILITY, "is_system": True},
    {"code": "3100", "name": "Owner's Equity", "account_type": AccountType.EQUITY, "is_system": True},
    {"code": "4010", "name": "Sales Revenue", "account_type": AccountType.REVENUE, "is_system": True},
    {"code": "5010", "name": "Cost of Goods Sold", "account_type": AccountType.EXPENSE, "is_system": False},
    {"code": "5100", "name": "Operating Expenses", "account_type": AccountType.EXPENSE, "is_system": False},
]
