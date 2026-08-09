"""
app/modules/accounting/models/core.py — Chart of Accounts & Journal Entries Core ORM Models
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Column, Date, Index, Numeric, UniqueConstraint, text
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin


# ── Enumerations ──────────────────────────────────────────────────────────────

class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class JournalEntryStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    VOIDED = "VOIDED"
    VOID = "VOIDED"  # Backwards-compatibility alias


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
    account_type: AccountType = Field(
        sa_column=Column(
            "account_type",
            sa.Enum(AccountType, name="accounttype", schema="tenant"),
            nullable=False,
        )
    )

    parent_id: UUID | None = Field(default=None, foreign_key="tenant.accounts.id")
    is_control: bool = Field(default=False)
    is_active: bool = Field(default=True)
    is_system: bool = Field(default=False)

    parent: Optional["Account"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Account.id"},
    )
    children: list["Account"] = Relationship(back_populates="parent")

    @property
    def type(self) -> AccountType:
        """Compatibility property alias for `account_type`."""
        return self.account_type

    @type.setter
    def type(self, value: AccountType):
        self.account_type = value


class PeriodStatus(StrEnum):
    """Accounting period status enumeration."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


# ── Accounting Period ─────────────────────────────────────────────────────────

class AccountingPeriod(TenantBase, table=True):
    __tablename__ = "accounting_periods"
    __table_args__ = ({"schema": "tenant"},)

    name: str = Field(max_length=100)
    start_date: datetime
    end_date: datetime
    is_closed: bool = Field(default=False)

    @property
    def status(self) -> PeriodStatus:
        """Return CLOSED if is_closed else OPEN."""
        return PeriodStatus.CLOSED if self.is_closed else PeriodStatus.OPEN

    @status.setter
    def status(self, value: PeriodStatus | str):
        val_str = str(value.value if isinstance(value, PeriodStatus) else value).upper()
        if val_str == "CLOSED":
            self.is_closed = True
        elif val_str == "OPEN":
            self.is_closed = False
        else:
            raise ValueError(f"Invalid period status: {value}")


# ── Journal Entry ─────────────────────────────────────────────────────────────

class JournalEntry(DocumentLifecycleMixin, TenantBase, table=True):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_status", "status"),
        Index("ix_journal_entries_created_at", "created_at"),
        {"schema": "tenant"},
    )

    reference: str | None = Field(default=None, max_length=100, index=True)
    reference_id: UUID | None = Field(default=None, index=True)
    entry_date: date = Field(
        default_factory=date.today,
        sa_column=Column(Date, nullable=False),
    )
    description: str = Field(max_length=2000)
    status: JournalEntryStatus = Field(
        default=JournalEntryStatus.DRAFT,
        sa_column=Column(
            sa.Enum(JournalEntryStatus, name="journalentrystatus", schema="tenant"),
            default=JournalEntryStatus.DRAFT,
            nullable=False,
        ),
    )

    source_type: str | None = Field(default=None, max_length=50)
    source_id: UUID | None = Field(default=None)
    source_event_id: UUID | None = Field(default=None)

    # V2 Enhancements
    branch_id: UUID | None = Field(default=None, index=True)
    entry_hash: str | None = Field(default=None, max_length=128)
    prev_hash: str | None = Field(default=None, max_length=128)
    sequence_no: int | None = Field(default=None, index=True)

    posted_at: datetime | None = Field(default=None)

    lines: list["JournalEntryLine"] = Relationship(
        back_populates="journal_entry",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


# ── Journal Entry Line ────────────────────────────────────────────────────────

class JournalEntryLine(TenantBase, table=True):
    __tablename__ = "journal_entry_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit >= 0 AND credit >= 0) "
            "AND NOT (debit > 0 AND credit > 0) "
            "AND (debit > 0 OR credit > 0)",
            name="ck_journal_entry_lines_debit_xor_credit",
        ),
        {"schema": "tenant"},
    )

    journal_entry_id: UUID = Field(foreign_key="tenant.journal_entries.id", index=True)
    account_id: UUID = Field(foreign_key="tenant.accounts.id", index=True)
    account_code: str | None = Field(default=None, max_length=20, index=True)
    account_name: str | None = Field(default=None, max_length=255)

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
    account: Optional[Account] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
    )


# ── Default Chart of Accounts Seed ────────────────────────────────────────────

DEFAULT_ACCOUNTS: list[dict] = [
    {"code": "1100", "name": "Cash & Cash Equivalents", "name_ar": "النقدية وما يعادلها", "type": AccountType.ASSET, "is_system": True},
    {"code": "1200", "name": "Accounts Receivable", "name_ar": "العملاء (حسابات مدينة)", "type": AccountType.ASSET, "is_system": True},
    {"code": "1300", "name": "Inventory", "name_ar": "المخزون", "type": AccountType.ASSET, "is_system": False},
    {"code": "2100", "name": "Accounts Payable", "name_ar": "الموردون (حسابات دائنة)", "type": AccountType.LIABILITY, "is_system": True},
    {"code": "3100", "name": "Owner's Equity", "name_ar": "حقوق الملكية", "type": AccountType.EQUITY, "is_system": True},
    {"code": "4010", "name": "Sales Revenue", "name_ar": "إيرادات المبيعات", "type": AccountType.REVENUE, "is_system": True},
    {"code": "5010", "name": "Cost of Goods Sold", "name_ar": "تكلفة البضاعة المباعة", "type": AccountType.EXPENSE, "is_system": False},
    {"code": "5100", "name": "Operating Expenses", "name_ar": "المصروفات التشغيلية", "type": AccountType.EXPENSE, "is_system": False},
]
