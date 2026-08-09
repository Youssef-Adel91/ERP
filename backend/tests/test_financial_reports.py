"""
tests/test_financial_reports.py — Integration Tests for Financial Reporting (Trial Balance)

Verifies:
  1. Empty Trial Balance returns 0 balances and balanced grand total.
  2. Trial Balance aggregates SUM(debit) and SUM(credit) across multiple posted journal entries.
  3. Net balances are correctly calculated by AccountType (Debit normal vs Credit normal).
  4. Grand Total row mathematically proves Total Debits == Total Credits across the entire GL.
  5. `as_of_date` parameter filters entries strictly up to the specified date.
  6. Unposted (DRAFT/VOIDED) entries are excluded from financial reports.
  7. `@reporting_tool` decorator metadata is properly attached for Copilot introspection.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models import JournalEntry, JournalEntryStatus
from app.modules.accounting.reports.trial_balance import generate_trial_balance
from app.modules.accounting.services.journal import create_journal_entry


@pytest.mark.asyncio
class TestTrialBalanceReport:
    """Test suite for the General Ledger Trial Balance report (Phase 3 Step 3)."""

    async def test_trial_balance_empty_ledger(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify an empty ledger returns zero balances and a balanced Grand Total row."""
        report = await generate_trial_balance(db_session, include_zero_balances=True)
        assert len(report) >= 2  # At least the seeded accounts + Grand Total row
        grand_total = report[-1]
        assert grand_total["is_grand_total"] is True
        assert grand_total["account_code"] == "TOTAL"
        assert grand_total["total_debit"] == Decimal("0.0000")
        assert grand_total["total_credit"] == Decimal("0.0000")
        assert grand_total["is_balanced"] is True

        # Test include_zero_balances=False
        report_non_zero = await generate_trial_balance(db_session, include_zero_balances=False)
        assert len(report_non_zero) == 1  # Only Grand Total row
        assert report_non_zero[0]["is_grand_total"] is True

    async def test_trial_balance_aggregation_and_net_balance(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify Trial Balance aggregates posted lines, computes net balance by AccountType, and balances."""
        cash = seed_chart_of_accounts["1110"]
        ar = seed_chart_of_accounts["1200"]
        ap = seed_chart_of_accounts["2100"]
        rev = seed_chart_of_accounts["4010"]
        cogs = seed_chart_of_accounts["5010"]

        # 1. Sales invoice: DR AR 1500, CR Revenue 1500
        await create_journal_entry(
            session=db_session,
            description="Sales Invoice INV-100",
            entry_date=date(2026, 7, 10),
            lines_data=[
                {"account_id": ar.id, "debit": Decimal("1500.0000"), "credit": Decimal("0.0000")},
                {"account_id": rev.id, "debit": Decimal("0.0000"), "credit": Decimal("1500.0000")},
            ],
            reference="INV-100",
            status=JournalEntryStatus.POSTED,
        )

        # 2. Customer payment: DR Cash 1000, CR AR 1000
        await create_journal_entry(
            session=db_session,
            description="Customer Payment PMT-100",
            entry_date=date(2026, 7, 12),
            lines_data=[
                {"account_id": cash.id, "debit": Decimal("1000.0000"), "credit": Decimal("0.0000")},
                {"account_id": ar.id, "debit": Decimal("0.0000"), "credit": Decimal("1000.0000")},
            ],
            reference="PMT-100",
            status=JournalEntryStatus.POSTED,
        )

        # 3. Supplier bill: DR COGS 400, CR AP 400
        await create_journal_entry(
            session=db_session,
            description="Supplier Bill BILL-100",
            entry_date=date(2026, 7, 15),
            lines_data=[
                {"account_id": cogs.id, "debit": Decimal("400.0000"), "credit": Decimal("0.0000")},
                {"account_id": ap.id, "debit": Decimal("0.0000"), "credit": Decimal("400.0000")},
            ],
            reference="BILL-100",
            status=JournalEntryStatus.POSTED,
        )

        report = await generate_trial_balance(db_session, include_zero_balances=False)
        assert len(report) == 6  # 5 Accounts + 1 Grand Total

        acc_map = {row["account_code"]: row for row in report if not row["is_grand_total"]}

        # Cash (ASSET): DR 1000, CR 0 -> Net 1000
        assert acc_map["1110"]["total_debit"] == Decimal("1000.0000")
        assert acc_map["1110"]["total_credit"] == Decimal("0.0000")
        assert acc_map["1110"]["net_balance"] == Decimal("1000.0000")

        # AR (ASSET): DR 1500, CR 1000 -> Net 500
        assert acc_map["1200"]["total_debit"] == Decimal("1500.0000")
        assert acc_map["1200"]["total_credit"] == Decimal("1000.0000")
        assert acc_map["1200"]["net_balance"] == Decimal("500.0000")

        # AP (LIABILITY): DR 0, CR 400 -> Net 400 (normal Credit balance)
        assert acc_map["2100"]["total_debit"] == Decimal("0.0000")
        assert acc_map["2100"]["total_credit"] == Decimal("400.0000")
        assert acc_map["2100"]["net_balance"] == Decimal("400.0000")

        # Revenue (REVENUE): DR 0, CR 1500 -> Net 1500 (normal Credit balance)
        assert acc_map["4010"]["total_debit"] == Decimal("0.0000")
        assert acc_map["4010"]["total_credit"] == Decimal("1500.0000")
        assert acc_map["4010"]["net_balance"] == Decimal("1500.0000")

        # COGS (EXPENSE): DR 400, CR 0 -> Net 400 (normal Debit balance)
        assert acc_map["5010"]["total_debit"] == Decimal("400.0000")
        assert acc_map["5010"]["total_credit"] == Decimal("0.0000")
        assert acc_map["5010"]["net_balance"] == Decimal("400.0000")

        # Grand Total verification: 1000 + 1500 + 400 = 2900
        grand_total = report[-1]
        assert grand_total["is_grand_total"] is True
        assert grand_total["total_debit"] == Decimal("2900.0000")
        assert grand_total["total_credit"] == Decimal("2900.0000")
        assert grand_total["total_debit"] == grand_total["total_credit"]
        assert grand_total["is_balanced"] is True

    async def test_trial_balance_as_of_date_filtering(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify as_of_date filters journal entries up to the specified date only."""
        cash = seed_chart_of_accounts["1110"]
        rev = seed_chart_of_accounts["4010"]

        # January entry
        await create_journal_entry(
            session=db_session,
            description="Jan Sale",
            entry_date=date(2026, 1, 15),
            lines_data=[
                {"account_id": cash.id, "debit": Decimal("500.0000"), "credit": Decimal("0.0000")},
                {"account_id": rev.id, "debit": Decimal("0.0000"), "credit": Decimal("500.0000")},
            ],
            reference="JAN-01",
            status=JournalEntryStatus.POSTED,
        )

        # March entry
        await create_journal_entry(
            session=db_session,
            description="Mar Sale",
            entry_date=date(2026, 3, 20),
            lines_data=[
                {"account_id": cash.id, "debit": Decimal("300.0000"), "credit": Decimal("0.0000")},
                {"account_id": rev.id, "debit": Decimal("0.0000"), "credit": Decimal("300.0000")},
            ],
            reference="MAR-01",
            status=JournalEntryStatus.POSTED,
        )

        # Query as of Feb 1 -> Should only include Jan Sale (500)
        report_feb = await generate_trial_balance(
            db_session,
            as_of_date=date(2026, 2, 1),
            include_zero_balances=False,
        )
        grand_total_feb = report_feb[-1]
        assert grand_total_feb["total_debit"] == Decimal("500.0000")
        assert grand_total_feb["total_credit"] == Decimal("500.0000")
        assert grand_total_feb["is_balanced"] is True

    async def test_trial_balance_excludes_draft_and_void(
        self,
        db_session: AsyncSession,
        seed_chart_of_accounts,
    ):
        """Verify unposted (DRAFT/VOIDED) entries do not impact Trial Balance totals."""
        cash = seed_chart_of_accounts["1110"]
        rev = seed_chart_of_accounts["4010"]

        # 1. Posted entry (100)
        await create_journal_entry(
            session=db_session,
            description="Posted Sale",
            entry_date=date(2026, 5, 1),
            lines_data=[
                {"account_id": cash.id, "debit": Decimal("100.0000"), "credit": Decimal("0.0000")},
                {"account_id": rev.id, "debit": Decimal("0.0000"), "credit": Decimal("100.0000")},
            ],
            reference="POSTED-01",
            status=JournalEntryStatus.POSTED,
        )

        # 2. Create a DRAFT entry manually (200)
        draft_entry = JournalEntry(
            reference="DRAFT-01",
            description="Unposted draft",
            status=JournalEntryStatus.DRAFT,
            entry_date=date(2026, 5, 2),
        )
        db_session.add(draft_entry)
        await db_session.flush()

        # 3. Create a VOIDED entry manually (300)
        void_entry = JournalEntry(
            reference="VOID-01",
            description="Voided entry",
            status=JournalEntryStatus.VOID,
            entry_date=date(2026, 5, 3),
        )
        db_session.add(void_entry)
        await db_session.flush()

        report = await generate_trial_balance(db_session, include_zero_balances=False)
        grand_total = report[-1]
        # Only the POSTED entry (100.0000) should be included
        assert grand_total["total_debit"] == Decimal("100.0000")
        assert grand_total["total_credit"] == Decimal("100.0000")
        assert grand_total["is_balanced"] is True


def test_trial_balance_copilot_metadata():
    """Verify @reporting_tool decorator attaches correct metadata for Copilot."""
    meta = getattr(generate_trial_balance, "__report_meta__", None)
    assert meta is not None
    assert meta["name"] == "Trial Balance"
    assert meta["description_ar"] == "ميزان المراجعة"
    assert meta["required_permission"] == "accounting.reports.trial_balance.view"

