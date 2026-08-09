"""
app/modules/finance/services/posting.py — COD Settlement GL Posting Engine & Period Close Gate (FR-770, FR-773, FR-780)

Implements:
  - post_settlement_to_gl: Posts a matched COD settlement to the general ledger using strict double-entry rules.
  - assert_period_close_gate: Validates unreconciled settlement exception threshold before closing an accounting period.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models.core import JournalEntry
from app.modules.accounting.services.journal import create_journal_entry
from app.modules.accounting.services.mappings import (
    AccountMappingKey,
    get_default_account,
)
from app.modules.finance.models.settlements import (
    CarrierSettlement,
    CarrierSettlementState,
    SettlementLine,
    SettlementLineMatchState,
)

logger = logging.getLogger(__name__)

FOUR_DECIMALS = Decimal("0.0001")


class SettlementPostingError(ValueError):
    """Raised when a settlement cannot be posted to the general ledger."""


class PeriodCloseGateError(ValueError):
    """Raised when an accounting period close is blocked by unreconciled settlement exceptions (FR-780)."""


async def post_settlement_to_gl(
    session: AsyncSession,
    settlement_id: UUID,
    description: str | None = None,
) -> JournalEntry:
    """
    Post a CarrierSettlement to the General Ledger (FR-770, FR-773, Section 10).

    Double-entry journal map:
      - DEBIT:  Treasury (Cash and Banks - 1100) for Net Remitted
      - DEBIT:  Shipping Expense (5200) for Shipping Fee total (if > 0)
      - DEBIT:  COD Fee Expense (5210) for COD Collection Fee total (if > 0)
      - DEBIT:  Return Fee Expense (5220) for Return Fee total (if > 0)
      - CREDIT: Cash with Carrier Control Account (1150) for Gross COD amount
    """
    stmt_settlement = select(CarrierSettlement).where(CarrierSettlement.id == settlement_id)
    res_settlement = await session.execute(stmt_settlement)
    settlement = res_settlement.scalars().first()

    if settlement is None:
        raise SettlementPostingError(f"Settlement with ID '{settlement_id}' not found.")

    if settlement.state == CarrierSettlementState.POSTED:
        raise SettlementPostingError(f"Settlement '{settlement.settlement_ref}' is already posted to GL.")

    if settlement.state not in (
        CarrierSettlementState.MATCHED,
        CarrierSettlementState.PARTIALLY_MATCHED,
    ):
        raise SettlementPostingError(
            f"Settlement in state '{settlement.state.value}' cannot be posted. Must be MATCHED or PARTIALLY_MATCHED.",
        )

    # Fetch settlement lines
    stmt_lines = select(SettlementLine).where(SettlementLine.settlement_id == settlement_id)
    res_lines = await session.execute(stmt_lines)
    lines = list(res_lines.scalars().all())

    total_gross = sum((line.cod_collected for line in lines), Decimal("0.0000")).quantize(FOUR_DECIMALS)
    total_shipping_fee = sum((line.shipping_fee for line in lines), Decimal("0.0000")).quantize(FOUR_DECIMALS)
    total_cod_fee = sum((line.cod_fee for line in lines), Decimal("0.0000")).quantize(FOUR_DECIMALS)
    total_return_fee = sum((line.return_fee for line in lines), Decimal("0.0000")).quantize(FOUR_DECIMALS)

    total_net = (total_gross - (total_shipping_fee + total_cod_fee + total_return_fee)).quantize(
        FOUR_DECIMALS,
    )

    if total_gross <= 0:
        raise SettlementPostingError("Cannot post settlement with zero or negative gross amount.")

    # Resolve default accounts
    acc_treasury = await get_default_account(session, AccountMappingKey.CASH_AND_BANKS)
    acc_control = await get_default_account(session, AccountMappingKey.CASH_WITH_CARRIER)
    acc_shipping = await get_default_account(session, AccountMappingKey.SHIPPING_EXPENSE)
    acc_cod_fee = await get_default_account(session, AccountMappingKey.COD_FEE_EXPENSE)
    acc_return_fee = await get_default_account(session, AccountMappingKey.RETURN_FEE_EXPENSE)

    lines_data: list[dict[str, Any]] = []

    # Debit lines
    if total_net != 0:
        lines_data.append(
            {
                "account_id": acc_treasury.id,
                "debit": total_net,
                "credit": Decimal("0.0000"),
                "description": f"Net COD Remittance - {settlement.carrier_code.upper()} {settlement.settlement_ref}",
            },
        )

    if total_shipping_fee > 0:
        lines_data.append(
            {
                "account_id": acc_shipping.id,
                "debit": total_shipping_fee,
                "credit": Decimal("0.0000"),
                "description": f"Carrier Delivery Fees - {settlement.carrier_code.upper()}",
            },
        )

    if total_cod_fee > 0:
        lines_data.append(
            {
                "account_id": acc_cod_fee.id,
                "debit": total_cod_fee,
                "credit": Decimal("0.0000"),
                "description": f"COD Collection Fees - {settlement.carrier_code.upper()}",
            },
        )

    if total_return_fee > 0:
        lines_data.append(
            {
                "account_id": acc_return_fee.id,
                "debit": total_return_fee,
                "credit": Decimal("0.0000"),
                "description": f"Carrier Return Fees - {settlement.carrier_code.upper()}",
            },
        )

    # Credit control account (gross COD)
    lines_data.append(
        {
            "account_id": acc_control.id,
            "debit": Decimal("0.0000"),
            "credit": total_gross,
            "description": f"COD Control Clearing - {settlement.carrier_code.upper()} {settlement.settlement_ref}",
        },
    )

    je_desc = (
        description
        or f"COD Settlement Posting — {settlement.carrier_code.upper()} Ref #{settlement.settlement_ref}"
    )

    journal_entry = await create_journal_entry(
        session=session,
        description=je_desc,
        lines_data=lines_data,
        reference_id=settlement_id,
        source_type="CARRIER_SETTLEMENT",
        source_id=settlement_id,
    )

    settlement.state = CarrierSettlementState.POSTED
    settlement.posted_at = datetime.now(UTC)
    settlement.journal_entry_id = journal_entry.id

    await session.flush()
    logger.info(
        "✅ Posted CarrierSettlement '%s' (ID: %s) to GL JournalEntry %s",
        settlement.settlement_ref,
        settlement_id,
        journal_entry.id,
    )
    return journal_entry


async def assert_period_close_gate(
    session: AsyncSession,
    period_end_date: date,
    max_unreconciled_exceptions: int = 0,
) -> int:
    """
    Architectural Refinement / Period Close Gate (FR-780):
    Asserts that unreconciled settlement exceptions (UNMATCHED or DISPUTED lines)
    do not exceed the allowed threshold prior to performing a Hard Close of an accounting period.

    Returns the count of unreconciled exceptions if within threshold.
    Raises PeriodCloseGateError if unreconciled exceptions exceed threshold.
    """
    end_dt = datetime.combine(period_end_date, datetime.max.time()).replace(tzinfo=UTC)

    stmt = (
        select(func.count(SettlementLine.id))
        .join(CarrierSettlement, SettlementLine.settlement_id == CarrierSettlement.id)
        .where(
            CarrierSettlement.created_at <= end_dt,
            SettlementLine.match_state.in_(
                [
                    SettlementLineMatchState.UNMATCHED,
                    SettlementLineMatchState.DISPUTED,
                ],
            ),
        )
    )
    res = await session.execute(stmt)
    unreconciled_count = int(res.scalar() or 0)

    if unreconciled_count > max_unreconciled_exceptions:
        raise PeriodCloseGateError(
            f"Period close blocked (FR-780): {unreconciled_count} unreconciled COD settlement "
            f"exceptions found (max allowed: {max_unreconciled_exceptions}). "
            "Resolve DISPUTED or UNMATCHED settlement lines before closing the period.",
        )

    return unreconciled_count
