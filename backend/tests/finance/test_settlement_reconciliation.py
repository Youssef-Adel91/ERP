"""
tests.finance.test_settlement_reconciliation — Test Suite for COD Settlement Matching & Posting (FR-770 to FR-780)

Tests:
  1. parse_settlement_file with Arabic and English header mappings.
  2. match_settlement with Exact AWB Matching (FR-771) and Fuzzy Matching (FR-772).
  3. Exception Queue Classification (FR-774) for amount mismatches, unknown AWBs, and non-delivered shipments.
  4. post_settlement_to_gl verifying strict double-entry balancing (SUM(debits) == SUM(credits)) at 4 decimals.
  5. generate_carrier_receivable_snapshot aging report generation across 0-7, 8-14, 15-30, 30+ days (FR-775).
  6. assert_period_close_gate blocking financial close when unreconciled exceptions exceed threshold (FR-780).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models.core import JournalEntryLine
from app.modules.finance.models.settlements import (
    CarrierSettlement,
    CarrierSettlementState,
    SettlementLine,
    SettlementLineExceptionType,
    SettlementLineMatchState,
)
from app.modules.finance.services.matching import (
    generate_carrier_receivable_snapshot,
    match_settlement,
    parse_settlement_file,
)
from app.modules.finance.services.posting import (
    PeriodCloseGateError,
    assert_period_close_gate,
    post_settlement_to_gl,
)
from app.modules.logistics.models.carriers import Shipment
from app.modules.logistics.services.shipments import ShipmentState

pytestmark = pytest.mark.asyncio


async def test_parse_settlement_file_arabic_english_headers():
    """Verify that parse_settlement_file handles both Arabic and English CSV headers."""
    csv_content = (
        "رقم_بوليصة,المبلغ_المحصل,رسوم_الشحن,رسوم_التحصيل,رسوم_المرتجع,رقم_الهاتف\n"
        "BST-001,1000.00,50.00,10.00,0.00,01012345678\n"
        "BST-002,2500.50,60.00,20.00,15.00,01198765432\n"
    ).encode("utf-8-sig")

    lines = parse_settlement_file(csv_content, "statement.csv")
    assert len(lines) == 2
    assert lines[0]["awb_number"] == "BST-001"
    assert lines[0]["cod_collected"] == Decimal("1000.0000")
    assert lines[0]["shipping_fee"] == Decimal("50.0000")
    assert lines[0]["cod_fee"] == Decimal("10.0000")
    assert lines[0]["phone_tail"] == "5678"

    assert lines[1]["awb_number"] == "BST-002"
    assert lines[1]["cod_collected"] == Decimal("2500.5000")
    assert lines[1]["return_fee"] == Decimal("15.0000")
    assert lines[1]["phone_tail"] == "5432"


async def test_exact_and_fuzzy_settlement_matching(db_session: AsyncSession, seed_tenant_and_users):
    """
    Verify Exact Matching (FR-771), Fuzzy Matching (FR-772), and Exception Queue (FR-774).
    """
    # 1. Seed Shipments
    ship_exact = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="bosta",
        awb_number="BST-EXACT-101",
        state=ShipmentState.DELIVERED,
        cod_amount=Decimal("1500.0000"),
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    ship_fuzzy = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="bosta",
        awb_number="BST-FUZZY-202",
        state=ShipmentState.DELIVERED,
        cod_amount=Decimal("2000.0000"),
        created_at=datetime.now(UTC) - timedelta(days=3),
    )
    ship_transit = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="bosta",
        awb_number="BST-TRANSIT-303",
        state=ShipmentState.IN_TRANSIT,
        cod_amount=Decimal("500.0000"),
        created_at=datetime.now(UTC) - timedelta(days=1),
    )

    db_session.add_all([ship_exact, ship_fuzzy, ship_transit])
    await db_session.flush()

    # 2. Prepare settlement statement lines
    lines = [
        {
            "awb_number": "BST-EXACT-101",
            "cod_collected": Decimal("1500.0000"),
            "shipping_fee": Decimal("50.0000"),
            "cod_fee": Decimal("10.0000"),
            "return_fee": Decimal("0.0000"),
            "phone_tail": "",
        },
        {
            "awb_number": "BST-TYPO-202",  # Typo in AWB -> Fuzzy Match by amount within date window
            "cod_collected": Decimal("2000.0000"),
            "shipping_fee": Decimal("60.0000"),
            "cod_fee": Decimal("15.0000"),
            "return_fee": Decimal("0.0000"),
            "phone_tail": "",
        },
        {
            "awb_number": "BST-TRANSIT-303",  # In transit -> Exception
            "cod_collected": Decimal("500.0000"),
            "shipping_fee": Decimal("20.0000"),
            "cod_fee": Decimal("5.0000"),
            "return_fee": Decimal("0.0000"),
            "phone_tail": "",
        },
        {
            "awb_number": "BST-UNKNOWN-999",  # Unknown -> Exception
            "cod_collected": Decimal("300.0000"),
            "shipping_fee": Decimal("10.0000"),
            "cod_fee": Decimal("0.0000"),
            "return_fee": Decimal("0.0000"),
            "phone_tail": "",
        },
    ]

    settlement = await match_settlement(
        session=db_session,
        carrier_code="bosta",
        settlement_ref="SET-2026-TEST",
        lines=lines,
        tolerance=Decimal("5.0000"),
    )

    assert settlement.state == CarrierSettlementState.PARTIALLY_MATCHED
    assert settlement.gross_amount == Decimal("4300.0000")
    assert settlement.total_fees == Decimal("170.0000")
    assert settlement.net_amount == Decimal("4130.0000")

    # Inspect lines
    stmt = select(SettlementLine).where(SettlementLine.settlement_id == settlement.id)
    s_lines = list((await db_session.execute(stmt)).scalars().all())
    assert len(s_lines) == 4

    l_exact = next(l for l in s_lines if l.awb_number == "BST-EXACT-101")
    assert l_exact.match_state == SettlementLineMatchState.MATCHED
    assert l_exact.exception_type == SettlementLineExceptionType.NONE
    assert l_exact.shipment_id == ship_exact.id

    l_fuzzy = next(l for l in s_lines if l.awb_number == "BST-TYPO-202")
    assert l_fuzzy.match_state == SettlementLineMatchState.FUZZY_MATCHED
    assert l_fuzzy.exception_type == SettlementLineExceptionType.NONE
    assert l_fuzzy.shipment_id == ship_fuzzy.id

    l_transit = next(l for l in s_lines if l.awb_number == "BST-TRANSIT-303")
    assert l_transit.match_state == SettlementLineMatchState.UNMATCHED
    assert l_transit.exception_type == SettlementLineExceptionType.REMITTED_BUT_NOT_DELIVERED

    l_unknown = next(l for l in s_lines if l.awb_number == "BST-UNKNOWN-999")
    assert l_unknown.match_state == SettlementLineMatchState.UNMATCHED
    assert l_unknown.exception_type == SettlementLineExceptionType.UNKNOWN_AWB


async def test_gl_posting_double_entry_balance(db_session: AsyncSession, seed_tenant_and_users):
    """
    Verify posting a matched settlement to GL produces a strictly balanced Journal Entry
    where SUM(debits) == SUM(credits) at 4 decimal places (FR-770, FR-773).
    """
    # 1. Seed Shipment
    ship = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="mylerz",
        awb_number="MYL-POST-01",
        state=ShipmentState.DELIVERED,
        cod_amount=Decimal("1000.0000"),
    )
    db_session.add(ship)
    await db_session.flush()

    # 2. Create matched settlement
    lines = [
        {
            "awb_number": "MYL-POST-01",
            "cod_collected": Decimal("1000.0000"),
            "shipping_fee": Decimal("50.0000"),
            "cod_fee": Decimal("10.0000"),
            "return_fee": Decimal("5.0000"),
            "phone_tail": "",
        },
    ]

    settlement = await match_settlement(
        session=db_session,
        carrier_code="mylerz",
        settlement_ref="MYL-SET-888",
        lines=lines,
    )
    assert settlement.state == CarrierSettlementState.MATCHED

    # 3. Post to GL
    journal_entry = await post_settlement_to_gl(db_session, settlement.id)

    assert settlement.state == CarrierSettlementState.POSTED
    assert settlement.journal_entry_id == journal_entry.id

    # 4. Assert double-entry balancing (SUM(debits) == SUM(credits))
    stmt = select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == journal_entry.id)
    je_lines = list((await db_session.execute(stmt)).scalars().all())

    total_debits = sum((l.debit for l in je_lines), Decimal("0.0000")).quantize(Decimal("0.0001"))
    total_credits = sum((l.credit for l in je_lines), Decimal("0.0000")).quantize(Decimal("0.0001"))

    assert total_debits == Decimal("1000.0000")
    assert total_credits == Decimal("1000.0000")
    assert total_debits == total_credits


async def test_aging_snapshot_generation(db_session: AsyncSession, seed_tenant_and_users):
    """
    Verify carrier receivable aging snapshot across 0-7, 8-14, 15-30, and 30+ days (FR-775).
    """
    now = datetime.now(UTC)
    s1 = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="bosta",
        awb_number="BST-AGE-01",
        state=ShipmentState.DELIVERED,
        cod_amount=Decimal("500.0000"),
        created_at=now - timedelta(days=5),  # 0-7 days
    )
    s2 = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="bosta",
        awb_number="BST-AGE-02",
        state=ShipmentState.DELIVERED,
        cod_amount=Decimal("800.0000"),
        created_at=now - timedelta(days=12),  # 8-14 days
    )
    s3 = Shipment(
        id=uuid4(),
        invoice_id=uuid4(),
        carrier_code="bosta",
        awb_number="BST-AGE-03",
        state=ShipmentState.DELIVERED,
        cod_amount=Decimal("1200.0000"),
        created_at=now - timedelta(days=40),  # 30+ days
    )

    db_session.add_all([s1, s2, s3])
    await db_session.flush()

    snapshot = await generate_carrier_receivable_snapshot(db_session, "bosta")

    assert snapshot.carrier_code == "bosta"
    assert snapshot.unsettled_shipments_count == 3
    assert snapshot.total_outstanding_cod == Decimal("2500.0000")
    assert snapshot.aging_0_7_days == Decimal("500.0000")
    assert snapshot.aging_8_14_days == Decimal("800.0000")
    assert snapshot.aging_15_30_days == Decimal("0.0000")
    assert snapshot.aging_30_plus_days == Decimal("1200.0000")


async def test_period_close_gate_fr780(db_session: AsyncSession, seed_tenant_and_users):
    """
    Architectural Refinement (FR-780):
    Verify that assert_period_close_gate blocks hard period closing when unreconciled
    exceptions exceed the allowed threshold.
    """
    # Create a settlement with 2 UNMATCHED exception lines
    settlement = CarrierSettlement(
        id=uuid4(),
        carrier_code="bosta",
        settlement_ref="SET-GATE-TEST",
        state=CarrierSettlementState.DISPUTED,
    )
    db_session.add(settlement)
    await db_session.flush()

    l1 = SettlementLine(
        settlement_id=settlement.id,
        awb_number="BST-ERR-01",
        cod_collected=Decimal("100.0000"),
        match_state=SettlementLineMatchState.UNMATCHED,
        exception_type=SettlementLineExceptionType.UNKNOWN_AWB,
    )
    l2 = SettlementLine(
        settlement_id=settlement.id,
        awb_number="BST-ERR-02",
        cod_collected=Decimal("200.0000"),
        match_state=SettlementLineMatchState.DISPUTED,
        exception_type=SettlementLineExceptionType.AMOUNT_MISMATCH,
    )
    db_session.add_all([l1, l2])
    await db_session.flush()

    # 1. Assert should raise error when max_unreconciled_exceptions=0
    with pytest.raises(PeriodCloseGateError) as exc_info:
        await assert_period_close_gate(
            session=db_session,
            period_end_date=date.today(),
            max_unreconciled_exceptions=0,
        )

    assert "Period close blocked (FR-780)" in str(exc_info.value)

    # 2. Assert should succeed when threshold allows >= 2 exceptions
    count = await assert_period_close_gate(
        session=db_session,
        period_end_date=date.today(),
        max_unreconciled_exceptions=5,
    )
    assert count == 2
