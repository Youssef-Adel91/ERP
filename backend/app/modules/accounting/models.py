"""
app/modules/accounting/models.py — Tenant-Schema Accounting ORM Models

CRITICAL DESIGN NOTE — No `schema=` in __table_args__:
  These tables have NO `schema=` annotation. SQLAlchemy will create them
  in whatever schema is active at the time of `create_all()` or `CREATE TABLE`.

  During tenant provisioning, `database.provision_tenant_schema()` calls:
      SET search_path TO tenant_{id}
      SQLModel.metadata.create_all(conn, tables=[...tenant tables...])

  This causes all these tables to land inside the new tenant schema.
  After that, every request sets search_path to the correct tenant schema,
  so all ORM queries target the right tables with zero extra code.

Double-Entry Enforcement:
  Layer 1 — Application: service.py raises UnbalancedEntryError before commit.
  Layer 2 — Pydantic:    schema validators reject bad payloads at the API layer.
  Layer 3 — Database:    CHECK constraint (debit XOR credit) per line.
  Layer 4 — DB Trigger:  `enforce_journal_balance` (added via Alembic migration).
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Numeric, UniqueConstraint, text
from sqlmodel import Column, Field, Relationship, SQLModel


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


class Account(SQLModel, table=True):
    """
    A single account in the Chart of Accounts.
    Stored per-tenant (no schema= annotation).

    Seeded automatically when a new tenant schema is provisioned.
    Default Egyptian ERP chart:
      1xxx — Assets    2xxx — Liabilities    3xxx — Equity
      4xxx — Revenue   5xxx — Expenses
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("code", name="uq_accounts_code"),
        Index("ix_accounts_type", "account_type"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=20, index=True)     # e.g. "1200", "4010"
    name: str = Field(max_length=255)                # e.g. "Accounts Receivable"
    name_ar: str | None = Field(default=None, max_length=255)
    account_type: AccountType
    is_active: bool = Field(default=True)
    is_system: bool = Field(default=False)           # Cannot be deleted

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )

    # Relationship to TransactionLine (via account code string, not UUID FK)
    transaction_lines: list["TransactionLine"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Account.code == foreign(TransactionLine.account_code)",
            "lazy": "select",
            "viewonly": True,
        }
    )


# ── Journal Entry ─────────────────────────────────────────────────────────────


class JournalEntry(SQLModel, table=True):
    """
    The atomic unit of double-entry accounting.

    A JournalEntry groups ≥ 2 TransactionLines where:
        Σ(debit lines) == Σ(credit lines)

    Once POSTED, an entry is immutable. Corrections require a reversing entry.
    """

    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_status", "status"),
        Index("ix_journal_entries_created_at", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    reference: str = Field(max_length=100, index=True)
    description: str = Field(max_length=2000)

    # Lifecycle: DRAFT → POSTED (immutable) | DRAFT → VOID
    status: JournalEntryStatus = Field(default=JournalEntryStatus.DRAFT)

    # Source linkage — traces which business event generated this entry
    source_type: str | None = Field(default=None, max_length=50)  # "invoice", "payment"
    source_id: UUID | None = Field(default=None)

    # Audit fields — UUID references to public.users (cross-schema, stored as UUID)
    created_by: UUID | None = Field(default=None)
    posted_by: UUID | None = Field(default=None)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )
    posted_at: datetime | None = Field(default=None)

    # Lines eagerly loaded (selectin) to avoid N+1 on list endpoints
    lines: list["TransactionLine"] = Relationship(
        back_populates="journal_entry",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


# ── Transaction Line ──────────────────────────────────────────────────────────


class TransactionLine(SQLModel, table=True):
    """
    A single debit or credit leg of a JournalEntry.

    account_code is a plain VARCHAR (not a UUID FK). This decouples transaction
    history from the Chart of Accounts, which is the correct accounting approach:
    even if an account is deactivated, historical entries remain valid and intact.

    Constraints enforced at this level:
      - debit >= 0 AND credit >= 0         (no negatives)
      - NOT (debit > 0 AND credit > 0)     (XOR — a line is one or the other)
      - NOT (debit == 0 AND credit == 0)   (must have value)

    The TOTAL balance constraint (Σdebits == Σcredits per entry) is enforced
    in service.py and by the PostgreSQL trigger defined in Alembic migration 002.
    """

    __tablename__ = "transaction_lines"
    __table_args__ = (
        # Line-level integrity: debit XOR credit, both non-negative, non-zero
        CheckConstraint(
            "(debit >= 0 AND credit >= 0) "
            "AND NOT (debit > 0 AND credit > 0) "
            "AND (debit > 0 OR credit > 0)",
            name="ck_transaction_lines_debit_xor_credit",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # FK to parent JournalEntry (UUID)
    journal_entry_id: UUID = Field(foreign_key="journal_entries.id", index=True)

    # Account identifier — stored as a code string (e.g. "1200", "4010")
    # Intentionally NOT a UUID FK. See docstring above.
    account_code: str = Field(max_length=20, index=True)

    # Human-readable account name snapshot at time of entry (for reporting)
    account_name: str = Field(max_length=255, default="")

    # Monetary amounts — Numeric(18,4) for EGP precision
    # Exactly ONE of (debit, credit) is > 0 per row
    debit: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )
    credit: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False, server_default=text("0")),
    )

    description: str | None = Field(default=None, max_length=500)

    # Relationship back to JournalEntry
    journal_entry: JournalEntry = Relationship(back_populates="lines")


# ── Default Chart of Accounts Seed ───────────────────────────────────────────

DEFAULT_ACCOUNTS: list[dict] = [
    # Assets
    {"code": "1100", "name": "Cash & Cash Equivalents",    "name_ar": "النقدية وما في حكمها",     "account_type": AccountType.ASSET,     "is_system": True},
    {"code": "1200", "name": "Accounts Receivable",         "name_ar": "المدينون / الذمم المدينة",  "account_type": AccountType.ASSET,     "is_system": True},
    {"code": "1300", "name": "Inventory",                   "name_ar": "المخزون",                   "account_type": AccountType.ASSET,     "is_system": False},
    # Liabilities
    {"code": "2100", "name": "Accounts Payable",            "name_ar": "الدائنون / الذمم الدائنة", "account_type": AccountType.LIABILITY, "is_system": True},
    # Equity
    {"code": "3100", "name": "Owner's Equity",              "name_ar": "حقوق الملكية",             "account_type": AccountType.EQUITY,    "is_system": True},
    # Revenue
    {"code": "4010", "name": "Sales Revenue",               "name_ar": "إيرادات المبيعات",         "account_type": AccountType.REVENUE,   "is_system": True},
    # Expenses
    {"code": "5010", "name": "Cost of Goods Sold",          "name_ar": "تكلفة البضاعة المباعة",    "account_type": AccountType.EXPENSE,   "is_system": False},
    {"code": "5100", "name": "Operating Expenses",          "name_ar": "المصروفات التشغيلية",       "account_type": AccountType.EXPENSE,   "is_system": False},
]
