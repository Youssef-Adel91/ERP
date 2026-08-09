"""
app/modules/accounting/reports/trial_balance.py — Trial Balance Report

Aggregates SUM(debit) and SUM(credit) from JournalEntryLine directly in the database,
grouped by Account, calculates net balance by AccountType, and appends a final
Grand Total row mathematically proving Total Debits == Total Credits across the entire GL.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reports.decorators import reporting_tool
from app.modules.accounting.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalEntryLine,
    JournalEntryStatus,
)
from app.modules.accounting.services.journal import FOUR_DECIMALS

logger = logging.getLogger(__name__)


@reporting_tool(
    name="Trial Balance",
    description_ar="ميزان المراجعة",
    required_permission="accounting.reports.trial_balance.view",
)
async def generate_trial_balance(
    session: AsyncSession,
    as_of_date: date | None = None,
    include_zero_balances: bool = True,
) -> list[dict[str, Any]]:
    """
    Generate a Trial Balance report aggregating posted journal entry lines
    by GL account directly at the database level.

    Calculates intelligent net balance by AccountType:
      - ASSET / EXPENSE: debit - credit (normal Debit balance)
      - LIABILITY / EQUITY / REVENUE: credit - debit (normal Credit balance)

    Appends a final Grand Total row verifying Total Debits == Total Credits.
    """
    # 1. Subquery for posted journal entry lines aggregated by account_id
    line_query = (
        select(
            JournalEntryLine.account_id,
            func.sum(JournalEntryLine.debit).label("sum_debit"),
            func.sum(JournalEntryLine.credit).label("sum_credit"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(JournalEntry.status == JournalEntryStatus.POSTED)
    )

    if as_of_date is not None:
        line_query = line_query.where(JournalEntry.entry_date <= as_of_date)

    line_subq = line_query.group_by(JournalEntryLine.account_id).subquery()

    # 2. Outer join Account with line_subq to get all accounts and their sums
    stmt = (
        select(
            Account.id.label("account_id"),
            Account.code.label("account_code"),
            Account.name.label("account_name"),
            Account.account_type.label("account_type"),
            func.coalesce(line_subq.c.sum_debit, Decimal("0")).label("total_debit"),
            func.coalesce(line_subq.c.sum_credit, Decimal("0")).label("total_credit"),
        )
        .select_from(Account)
        .outerjoin(line_subq, Account.id == line_subq.c.account_id)
        .order_by(Account.code.asc())
    )

    res = await session.execute(stmt)
    rows = res.all()

    report: list[dict[str, Any]] = []
    grand_total_debit = Decimal("0.0000")
    grand_total_credit = Decimal("0.0000")

    for row in rows:
        debit = Decimal(str(row.total_debit)).quantize(FOUR_DECIMALS)
        credit = Decimal(str(row.total_credit)).quantize(FOUR_DECIMALS)

        if not include_zero_balances and debit == Decimal("0.0000") and credit == Decimal("0.0000"):
            continue

        # Determine net balance based on normal balance direction of AccountType
        acc_type = row.account_type
        type_str = acc_type.value if hasattr(acc_type, "value") else str(acc_type)

        if type_str in (AccountType.ASSET.value, AccountType.EXPENSE.value):
            net_balance = (debit - credit).quantize(FOUR_DECIMALS)
        else:
            net_balance = (credit - debit).quantize(FOUR_DECIMALS)

        report.append(
            {
                "account_id": str(row.account_id),
                "account_code": row.account_code,
                "account_name": row.account_name,
                "account_type": type_str,
                "total_debit": debit,
                "total_credit": credit,
                "net_balance": net_balance,
                "is_grand_total": False,
            }
        )

        grand_total_debit += debit
        grand_total_credit += credit

    # 3. Append final Grand Total row mathematically proving Total Debits == Total Credits
    grand_total_debit = grand_total_debit.quantize(FOUR_DECIMALS)
    grand_total_credit = grand_total_credit.quantize(FOUR_DECIMALS)
    is_balanced = grand_total_debit == grand_total_credit

    report.append(
        {
            "account_id": None,
            "account_code": "TOTAL",
            "account_name": "Grand Total",
            "account_type": "TOTAL",
            "total_debit": grand_total_debit,
            "total_credit": grand_total_credit,
            "net_balance": (grand_total_debit - grand_total_credit).quantize(FOUR_DECIMALS),
            "is_grand_total": True,
            "is_balanced": is_balanced,
        }
    )

    return report
