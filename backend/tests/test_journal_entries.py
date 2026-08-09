"""
tests/test_journal_entries.py — Phase 3 Step 1: Chart of Accounts & Journal Entries Tests

Tests:
  1. Chart of Accounts hierarchy (parent / children relationships)
  2. Compatibility aliases (TransactionLine == JournalEntryLine, Account.type == Account.account_type)
  3. Double-entry engine strict balance enforcement (4 decimal places precision)
  4. UnbalancedJournalEntryError exception and database rollback
  5. Package re-exports from app.modules.accounting.models
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
    TransactionLine,
)
from app.modules.accounting.services.journal import (
    UnbalancedJournalEntryError,
    create_journal_entry,
)


@pytest.mark.asyncio
class TestChartOfAccountsAndAliases:
    """Tests for Core Chart of Accounts models and backwards-compatible aliases."""

    async def test_account_type_and_aliases(self, db_session: AsyncSession, seed_tenant_and_users):
        """Verify AccountType enum and that Account.type acts as alias for Account.account_type."""
        acc_id = uuid4()
        account = Account(
            id=acc_id,
            code="1000",
            name="Current Assets Control",
            account_type=AccountType.ASSET,
            is_control=True,
        )
        # Verify alias property
        assert account.type == AccountType.ASSET
        account.type = AccountType.LIABILITY
        assert account.account_type == AccountType.LIABILITY

        # Restore to ASSET
        account.type = AccountType.ASSET
        db_session.add(account)
        await db_session.commit()

        fetched = await db_session.get(Account, acc_id)
        assert fetched is not None
        assert fetched.type == AccountType.ASSET

    async def test_chart_of_accounts_hierarchy(self, db_session: AsyncSession, seed_tenant_and_users):
        """Verify parent and child relationship in hierarchical Chart of Accounts."""
        parent_id = uuid4()
        child_id = uuid4()

        parent_acc = Account(
            id=parent_id,
            code="11000",
            name="Cash Control",
            account_type=AccountType.ASSET,
            is_control=True,
        )
        child_acc = Account(
            id=child_id,
            code="11010",
            name="Petty Cash",
            account_type=AccountType.ASSET,
            parent_id=parent_id,
            is_control=False,
        )

        db_session.add(parent_acc)
        db_session.add(child_acc)
        await db_session.commit()

        # Verify query and hierarchy linkage
        stmt = select(Account).where(Account.id == child_id)
        res = await db_session.execute(stmt)
        child_db = res.scalar_one()
        assert child_db.parent_id == parent_id

    async def test_transaction_line_alias_is_identical(self):
        """Verify that TransactionLine is an alias for JournalEntryLine."""
        assert TransactionLine is JournalEntryLine


@pytest.mark.asyncio
class TestDoubleEntryEngine:
    """Tests for Phase 3 Double-Entry Engine service (create_journal_entry)."""

    async def test_create_journal_entry_balanced(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """create_journal_entry succeeds when SUM(debits) == SUM(credits) to 4 decimal places."""
        ar = seed_chart_of_accounts["1200"]
        rev = seed_chart_of_accounts["4010"]

        entry = await create_journal_entry(
            session=db_session,
            reference="JE-PHASE3-001",
            description="Phase 3 Balanced Test",
            lines=[
                {"account_id": ar.id, "account_code": ar.code, "debit": Decimal("1250.5500"), "credit": Decimal("0.0000")},
                {"account_id": rev.id, "account_code": rev.code, "debit": Decimal("0.0000"), "credit": Decimal("1250.5500")},
            ],
            status=JournalEntryStatus.POSTED,
        )

        assert entry.id is not None
        assert entry.status == JournalEntryStatus.POSTED
        assert len(entry.lines) == 2

        # Verify DB persistence
        from sqlalchemy.orm import selectinload
        stmt = select(JournalEntry).where(JournalEntry.id == entry.id).options(selectinload(JournalEntry.lines))
        res = await db_session.execute(stmt)
        db_entry = res.scalar_one()
        assert len(db_entry.lines) == 2
        total_dr = sum(l.debit for l in db_entry.lines)
        total_cr = sum(l.credit for l in db_entry.lines)
        assert total_dr == total_cr == Decimal("1250.5500")

    async def test_create_journal_entry_unbalanced_raises_and_rollback(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """create_journal_entry raises UnbalancedJournalEntryError when debits != credits and rolls back."""
        ar = seed_chart_of_accounts["1200"]
        rev = seed_chart_of_accounts["4010"]

        with pytest.raises(UnbalancedJournalEntryError) as exc_info:
            await create_journal_entry(
                session=db_session,
                reference="JE-UNBALANCED-001",
                description="Unbalanced Entry Should Fail",
                lines=[
                    {"account_id": ar.id, "account_code": ar.code, "debit": Decimal("1000.0000"), "credit": Decimal("0.0000")},
                    {"account_id": rev.id, "account_code": rev.code, "debit": Decimal("0.0000"), "credit": Decimal("999.9900")},
                ],
            )
        assert "unbalanced" in str(exc_info.value).lower()

        # Verify no entry with reference JE-UNBALANCED-001 was persisted
        stmt = select(JournalEntry).where(JournalEntry.reference == "JE-UNBALANCED-001")
        res = await db_session.execute(stmt)
        assert res.scalar_one_or_none() is None

    async def test_create_journal_entry_4th_decimal_precision(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """Verify strict quantization to 4 decimal places (Decimal('18.4'))."""
        ar = seed_chart_of_accounts["1200"]
        rev = seed_chart_of_accounts["4010"]

        # 0.3333 + 0.3333 + 0.3334 = 1.0000
        entry = await create_journal_entry(
            session=db_session,
            reference="JE-PRECISION-001",
            description="4th Decimal Place Test",
            lines=[
                {"account_id": ar.id, "account_code": ar.code, "debit": Decimal("0.3333"), "credit": Decimal("0.0000")},
                {"account_id": ar.id, "account_code": ar.code, "debit": Decimal("0.3333"), "credit": Decimal("0.0000")},
                {"account_id": ar.id, "account_code": ar.code, "debit": Decimal("0.3334"), "credit": Decimal("0.0000")},
                {"account_id": rev.id, "account_code": rev.code, "debit": Decimal("0.0000"), "credit": Decimal("1.0000")},
            ],
        )

        assert entry.id is not None
        assert len(entry.lines) == 4
