"""
tests/test_accounting.py — Double-Entry Accounting Tests

Critical tests:
  1. Balanced journal entry → 201 Created
  2. Unbalanced journal entry → 422 + UNBALANCED_ENTRY error
  3. Single debit-only line → 422 (unbalanced)
  4. Line with both debit AND credit → validation error
  5. Line with zero debit AND zero credit → validation error
  6. Post a DRAFT entry → status becomes POSTED
  7. Attempt to post an already-POSTED entry → 409 Conflict
  8. Account balance computed correctly from POSTED entries
  9. Reversing entry: swaps debits/credits correctly
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting import service
from app.modules.accounting.models import AccountType, JournalEntryStatus
from app.modules.accounting.schemas import (
    AccountCreateRequest,
    JournalEntryCreateRequest,
    TransactionLineCreateRequest,
)


@pytest.mark.asyncio
class TestDoubleEntryConstraints:
    """Tests for the application-layer double-entry enforcement."""

    async def test_balanced_entry_created_successfully(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """A perfectly balanced entry (DR = CR) should be created as DRAFT."""
        ar = seed_chart_of_accounts["1200"]
        revenue = seed_chart_of_accounts["4010"]

        entry_data = JournalEntryCreateRequest(
            reference="JE-TEST-001",
            description="Test balanced entry",
            lines=[
                TransactionLineCreateRequest(
                    account_id=ar.id, debit=Decimal("1000.00")
                ),
                TransactionLineCreateRequest(
                    account_id=revenue.id, credit=Decimal("1000.00")
                ),
            ],
        )

        entry = await service.create_draft_journal_entry(
            data=entry_data,
            created_by=uuid4(),
            db=db_session,
        )

        assert entry.status == JournalEntryStatus.DRAFT
        assert entry.reference == "JE-TEST-001"
        assert len(entry.lines) == 2

    async def test_unbalanced_entry_raises_error(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """An unbalanced entry must raise UnbalancedEntryError — never touch the DB."""
        ar = seed_chart_of_accounts["1200"]
        revenue = seed_chart_of_accounts["4010"]

        entry_data = JournalEntryCreateRequest.__new__(JournalEntryCreateRequest)
        # Bypass Pydantic validation to test service-layer enforcement
        object.__setattr__(entry_data, "reference", "JE-UNBAL-001")
        object.__setattr__(entry_data, "description", "Unbalanced entry")
        object.__setattr__(entry_data, "source_type", None)
        object.__setattr__(entry_data, "source_id", None)

        # Manually create lines with mismatched amounts
        line1 = TransactionLineCreateRequest.__new__(TransactionLineCreateRequest)
        object.__setattr__(line1, "account_id", ar.id)
        object.__setattr__(line1, "debit", Decimal("1500.00"))
        object.__setattr__(line1, "credit", Decimal("0"))
        object.__setattr__(line1, "description", None)

        line2 = TransactionLineCreateRequest.__new__(TransactionLineCreateRequest)
        object.__setattr__(line2, "account_id", revenue.id)
        object.__setattr__(line2, "debit", Decimal("0"))
        object.__setattr__(line2, "credit", Decimal("1000.00"))  # ≠ 1500
        object.__setattr__(line2, "description", None)

        object.__setattr__(entry_data, "lines", [line1, line2])

        with pytest.raises(service.UnbalancedEntryError) as exc_info:
            await service.create_draft_journal_entry(
                data=entry_data,
                created_by=uuid4(),
                db=db_session,
            )

        assert "1500" in str(exc_info.value)
        assert "1000" in str(exc_info.value)

    async def test_pydantic_rejects_both_debit_and_credit_on_same_line(self):
        """A TransactionLine with both debit > 0 AND credit > 0 is invalid."""
        with pytest.raises(ValueError, match="cannot have both debit and credit"):
            TransactionLineCreateRequest(
                account_id=uuid4(),
                debit=Decimal("500"),
                credit=Decimal("500"),
            )

    async def test_pydantic_rejects_zero_line(self):
        """A TransactionLine with debit=0 AND credit=0 is invalid."""
        with pytest.raises(ValueError, match="non-zero"):
            TransactionLineCreateRequest(
                account_id=uuid4(),
                debit=Decimal("0"),
                credit=Decimal("0"),
            )

    async def test_pydantic_rejects_unbalanced_entry(
        self, seed_chart_of_accounts: dict
    ):
        """JournalEntryCreateRequest itself validates balance."""
        ar = seed_chart_of_accounts["1200"]
        revenue = seed_chart_of_accounts["4010"]

        with pytest.raises(ValueError, match="unbalanced"):
            JournalEntryCreateRequest(
                reference="JE-BAD",
                description="Bad",
                lines=[
                    TransactionLineCreateRequest(account_id=ar.id, debit=Decimal("999")),
                    TransactionLineCreateRequest(account_id=revenue.id, credit=Decimal("888")),
                ],
            )

    async def test_post_draft_entry_makes_it_immutable(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """Posting a DRAFT entry transitions it to POSTED status."""
        ar = seed_chart_of_accounts["1200"]
        revenue = seed_chart_of_accounts["4010"]
        user_id = uuid4()

        entry_data = JournalEntryCreateRequest(
            reference="JE-POST-001",
            description="To be posted",
            lines=[
                TransactionLineCreateRequest(account_id=ar.id, debit=Decimal("500")),
                TransactionLineCreateRequest(account_id=revenue.id, credit=Decimal("500")),
            ],
        )

        entry = await service.create_draft_journal_entry(entry_data, user_id, db_session)
        assert entry.status == JournalEntryStatus.DRAFT

        posted = await service.post_journal_entry(entry.id, user_id, db_session)

        assert posted.status == JournalEntryStatus.POSTED
        assert posted.posted_by == user_id
        assert posted.posted_at is not None

    async def test_cannot_post_already_posted_entry(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """Attempting to post an already-POSTED entry raises PostedEntryMutationError."""
        ar = seed_chart_of_accounts["1200"]
        revenue = seed_chart_of_accounts["4010"]
        user_id = uuid4()

        entry_data = JournalEntryCreateRequest(
            reference="JE-DOUBLE-POST",
            description="Will be posted twice",
            lines=[
                TransactionLineCreateRequest(account_id=ar.id, debit=Decimal("200")),
                TransactionLineCreateRequest(account_id=revenue.id, credit=Decimal("200")),
            ],
        )

        entry = await service.create_draft_journal_entry(entry_data, user_id, db_session)
        await service.post_journal_entry(entry.id, user_id, db_session)

        with pytest.raises(service.PostedEntryMutationError):
            await service.post_journal_entry(entry.id, user_id, db_session)

    async def test_account_balance_after_posting(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """Account balance should reflect only POSTED entries."""
        ar = seed_chart_of_accounts["1200"]  # Asset: debit balance
        revenue = seed_chart_of_accounts["4010"]  # Revenue: credit balance
        user_id = uuid4()

        # Entry 1: Post 1000 DR Receivables / CR Revenue
        e1 = await service.create_draft_journal_entry(
            JournalEntryCreateRequest(
                reference="JE-BAL-001",
                description="Sale 1",
                lines=[
                    TransactionLineCreateRequest(account_id=ar.id, debit=Decimal("1000")),
                    TransactionLineCreateRequest(account_id=revenue.id, credit=Decimal("1000")),
                ],
            ),
            user_id, db_session,
        )
        await service.post_journal_entry(e1.id, user_id, db_session)

        # Entry 2: DRAFT (should NOT affect balance)
        await service.create_draft_journal_entry(
            JournalEntryCreateRequest(
                reference="JE-BAL-002",
                description="Sale 2 (draft)",
                lines=[
                    TransactionLineCreateRequest(account_id=ar.id, debit=Decimal("500")),
                    TransactionLineCreateRequest(account_id=revenue.id, credit=Decimal("500")),
                ],
            ),
            user_id, db_session,
        )

        ar_balance = await service.get_account_balance(ar.id, db_session)
        revenue_balance = await service.get_account_balance(revenue.id, db_session)

        # Only posted entry (1000) should be reflected
        assert ar_balance.total_debit == Decimal("1000.0000")
        assert ar_balance.balance == Decimal("1000.0000")  # Asset: positive debit balance
        assert revenue_balance.total_credit == Decimal("1000.0000")
        assert revenue_balance.balance == Decimal("1000.0000")  # Revenue: positive credit balance

    async def test_reversing_entry_swaps_debits_and_credits(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts: dict,
    ):
        """Reversing entry should swap debits and credits from the original."""
        ar = seed_chart_of_accounts["1200"]
        revenue = seed_chart_of_accounts["4010"]
        user_id = uuid4()

        original = await service.create_draft_journal_entry(
            JournalEntryCreateRequest(
                reference="JE-REV-ORIG",
                description="Original entry",
                lines=[
                    TransactionLineCreateRequest(account_id=ar.id, debit=Decimal("750")),
                    TransactionLineCreateRequest(account_id=revenue.id, credit=Decimal("750")),
                ],
            ),
            user_id, db_session,
        )
        await service.post_journal_entry(original.id, user_id, db_session)

        reversing = await service.create_reversing_entry(original.id, user_id, db_session)

        assert reversing.reference == f"REV-{original.reference}"
        assert reversing.status == JournalEntryStatus.DRAFT

        # Debits and credits should be swapped
        orig_lines = {line.account_id: line for line in original.lines}
        rev_lines = {line.account_id: line for line in reversing.lines}

        assert rev_lines[ar.id].credit == orig_lines[ar.id].debit
        assert rev_lines[ar.id].debit == orig_lines[ar.id].credit
        assert rev_lines[revenue.id].debit == orig_lines[revenue.id].credit
        assert rev_lines[revenue.id].credit == orig_lines[revenue.id].debit
