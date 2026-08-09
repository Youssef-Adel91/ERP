"""
tests/test_period_closing.py — Integration Tests for Period Management (The Hard Block)

Verifies that:
  1. Posting into an OPEN accounting period succeeds.
  2. Posting into a CLOSED accounting period immediately raises ClosedPeriodError and rolls back.
  3. Posting into a date with NO defined accounting period raises ClosedPeriodError.
  4. Closing an open period blocks subsequent postings into that period.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import (
    Account,
    AccountingPeriod,
    AccountType,
    JournalEntry,
    PeriodStatus,
)
from app.modules.accounting.services.journal import ClosedPeriodError, create_journal_entry


@pytest.mark.asyncio
class TestPeriodClosingHardBlock:
    """Test suite for Accounting Period validation and transaction abort hooks."""

    async def _get_test_accounts(self, session: AsyncSession) -> tuple[Account, Account]:
        """Helper to retrieve ASSET and REVENUE accounts for testing."""
        accounts = (await session.execute(select(Account))).scalars().all()
        asset_acc = next(a for a in accounts if a.account_type == AccountType.ASSET)
        rev_acc = next(a for a in accounts if a.account_type == AccountType.REVENUE)
        return asset_acc, rev_acc

    async def test_post_into_open_period_succeeds(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify posting into an OPEN period succeeds normally."""
        asset_acc, rev_acc = await self._get_test_accounts(db_session)

        entry = await create_journal_entry(
            session=db_session,
            description="Valid entry in open period",
            entry_date=date(2026, 7, 28),
            lines_data=[
                {"account_id": asset_acc.id, "debit": Decimal("500.0000"), "credit": Decimal("0.0000")},
                {"account_id": rev_acc.id, "debit": Decimal("0.0000"), "credit": Decimal("500.0000")},
            ],
            reference="OPEN-TEST-01",
        )
        assert entry.id is not None
        assert entry.entry_date == date(2026, 7, 28)

    async def test_post_into_closed_period_raises_and_rollback(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify attempting to post into a CLOSED period raises ClosedPeriodError and rolls back."""
        asset_acc, rev_acc = await self._get_test_accounts(db_session)

        # Create a CLOSED accounting period for FY2019
        closed_period = AccountingPeriod(
            id=uuid4(),
            name="FY2019 - Closed",
            start_date=datetime(2019, 1, 1, tzinfo=UTC),
            end_date=datetime(2019, 12, 31, 23, 59, 59, tzinfo=UTC),
            is_closed=True,
        )
        db_session.add(closed_period)
        await db_session.commit()

        # Verify PeriodStatus property alias
        assert closed_period.status == PeriodStatus.CLOSED

        test_date = date(2019, 6, 15)

        with pytest.raises(ClosedPeriodError) as exc_info:
            await create_journal_entry(
                session=db_session,
                description="Attempt to post into closed FY2019",
                entry_date=test_date,
                lines_data=[
                    {"account_id": asset_acc.id, "debit": Decimal("1000.0000"), "credit": Decimal("0.0000")},
                    {"account_id": rev_acc.id, "debit": Decimal("0.0000"), "credit": Decimal("1000.0000")},
                ],
                reference="CLOSED-TEST-01",
            )

        assert "is CLOSED" in str(exc_info.value)

        # Verify no entry was persisted in the database for that date/reference
        stmt = select(JournalEntry).where(JournalEntry.reference == "CLOSED-TEST-01")
        res = await db_session.execute(stmt)
        assert res.scalar_one_or_none() is None

    async def test_post_into_undefined_period_raises(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify attempting to post into a date with NO defined accounting period raises ClosedPeriodError."""
        asset_acc, rev_acc = await self._get_test_accounts(db_session)

        test_date = date(1999, 5, 1)  # Outside all seeded periods

        with pytest.raises(ClosedPeriodError) as exc_info:
            await create_journal_entry(
                session=db_session,
                description="Attempt to post outside any period",
                entry_date=test_date,
                lines_data=[
                    {"account_id": asset_acc.id, "debit": Decimal("300.0000"), "credit": Decimal("0.0000")},
                    {"account_id": rev_acc.id, "debit": Decimal("0.0000"), "credit": Decimal("300.0000")},
                ],
                reference="UNDEFINED-TEST-01",
            )

        assert "No accounting period defined" in str(exc_info.value)

        stmt = select(JournalEntry).where(JournalEntry.reference == "UNDEFINED-TEST-01")
        res = await db_session.execute(stmt)
        assert res.scalar_one_or_none() is None

    async def test_closing_open_period_blocks_subsequent_postings(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify that transitioning a period from OPEN to CLOSED immediately blocks future postings."""
        asset_acc, rev_acc = await self._get_test_accounts(db_session)

        period_2018 = AccountingPeriod(
            id=uuid4(),
            name="FY2018",
            start_date=datetime(2018, 1, 1, tzinfo=UTC),
            end_date=datetime(2018, 12, 31, 23, 59, 59, tzinfo=UTC),
            is_closed=False,
        )
        db_session.add(period_2018)
        await db_session.commit()

        # 1. Post while open -> SUCCEEDS
        entry1 = await create_journal_entry(
            session=db_session,
            description="Entry while period is open",
            entry_date=date(2018, 3, 15),
            lines_data=[
                {"account_id": asset_acc.id, "debit": Decimal("250.0000"), "credit": Decimal("0.0000")},
                {"account_id": rev_acc.id, "debit": Decimal("0.0000"), "credit": Decimal("250.0000")},
            ],
            reference="2018-OPEN",
        )
        assert entry1.id is not None

        # 2. Close the period using status setter
        period_2018.status = PeriodStatus.CLOSED
        await db_session.commit()
        assert period_2018.is_closed is True

        # 3. Attempt to post another entry -> FAILS WITH CLOSED PERIOD ERROR
        with pytest.raises(ClosedPeriodError):
            await create_journal_entry(
                session=db_session,
                description="Entry after period is closed",
                entry_date=date(2018, 4, 15),
                lines_data=[
                    {"account_id": asset_acc.id, "debit": Decimal("250.0000"), "credit": Decimal("0.0000")},
                    {"account_id": rev_acc.id, "debit": Decimal("0.0000"), "credit": Decimal("250.0000")},
                ],
                reference="2018-CLOSED",
            )
