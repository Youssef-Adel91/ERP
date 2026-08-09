"""
tests/purchasing/test_supplier_payments_fx.py — Integration tests for Phase 4b Step 4: Supplier Payments & FX Settlement

Covers:
  1. Realized FX Loss calculation & GL Bridge (Rate D > Rate C -> DEBIT FX Variance Expense).
  2. Realized FX Gain calculation & GL Bridge (Rate D < Rate C -> CREDIT FX Variance Expense).
  3. Payment allocation rules and validations (over-allocation, duplicate allocation, draft bill check).
  4. Alembic migration verification for Phase 4b Step 4.
"""
from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.events.event_bus import DomainEvent
from app.modules.accounting.consumers.purchasing_events import handle_payment_made
from app.modules.accounting.models.core import (
    JournalEntry,
    JournalEntryLine as TransactionLine,
    JournalEntryStatus,
)
from app.modules.accounting.services.mappings import AccountMappingKey, get_default_account_id
from app.modules.purchasing.exceptions import PaymentAllocationError
from app.modules.purchasing.models.billing import (
    VendorBill,
    VendorBillMatchState,
    VendorBillStatus,
)
from app.modules.purchasing.models.payments import SupplierPayment, SupplierPaymentStatus
from app.modules.purchasing.services.billing import (
    create_vendor_bill,
    execute_three_way_match,
    post_vendor_bill,
)
from app.modules.purchasing.services.orders import confirm_purchase_order, create_purchase_order
from app.modules.purchasing.services.payments import (
    allocate_payment,
    create_supplier_payment,
    post_supplier_payment,
)
from app.modules.purchasing.services.receiving import receive_goods
from app.modules.system.models import OutboxEvent


@pytest.mark.asyncio
async def test_supplier_payment_fx_loss_and_gl_bridge(db_session: AsyncSession, seed_tenant_and_users):
    """
    Test Phase 4b Step 4: Supplier Payments with Realized FX Loss.
    1. Bill Date Rate C = 50.000000 for 100 USD -> Base AP Liability cleared = 5,000 EGP.
    2. Payment Date Rate D = 52.000000 for 100 USD -> Base Treasury Paid = 5,200 EGP.
    3. fx_gain_loss_amount = +200.0000 EGP (Realized FX Loss).
    4. Post payment -> check GL Bridge (DR AP 5000, CR Treasury 5200, DR FX Variance Expense 200).
    5. Check idempotency on duplicate event.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()
    treasury_id = uuid4()

    # 1. PO + GRN + Bill in USD @ Rate C = 50.000000
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "item_id": uuid4(),
                "qty_ordered": "10.0000",
                "unit_price": "10.0000",  # Total 100 USD
            }
        ],
        currency="USD",
    )
    await confirm_purchase_order(db_session, po.id)
    po_line = po.lines[0]

    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po.id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "item_id": po_line.item_id,
                "qty_received": "10.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=f"GRN-FXL-{uuid4().hex[:6]}",
    )

    bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-FXL-{uuid4().hex[:6]}",
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "grn_line_id": str(grn.lines[0].id),
                "qty_billed": "10.0000",
                "unit_price": "10.0000",
            }
        ],
        currency="USD",
        fx_rate=Decimal("50.000000"),
    )
    await execute_three_way_match(db_session, bill.id)
    posted_bill = await post_vendor_bill(db_session, bill.id)
    assert posted_bill.status == VendorBillStatus.POSTED

    # 2. Create SupplierPayment in USD @ Rate D = 52.000000
    payment_number = f"PAY-FXL-{uuid4().hex[:6]}"
    payment = await create_supplier_payment(
        session=db_session,
        supplier_id=supplier_id,
        treasury_id=treasury_id,
        payment_number=payment_number,
        amount=Decimal("100.0000"),
        currency="USD",
        fx_rate=Decimal("52.000000"),
    )
    assert payment.status == SupplierPaymentStatus.DRAFT

    # 3. Allocate Payment to VendorBill
    payment = await allocate_payment(
        session=db_session,
        payment_id=payment.id,
        bill_id=bill.id,
        allocated_amount=Decimal("100.0000"),
    )
    # Base Paid = 100 * 52 = 5200; Base Cleared = 100 * 50 = 5000
    # FX Gain/Loss = 5200 - 5000 = +200.0000 (Loss)
    assert payment.fx_gain_loss_amount == Decimal("200.0000")

    # 4. Post Payment -> Emits purchase.payment_made outbox event
    posted_payment = await post_supplier_payment(db_session, payment.id)
    assert posted_payment.status == SupplierPaymentStatus.POSTED

    stmt = select(OutboxEvent).where(OutboxEvent.event_type == "purchase.payment_made")
    res = await db_session.execute(stmt)
    outbox_events = res.scalars().all()
    assert len(outbox_events) >= 1
    event_row = outbox_events[-1]
    payload = event_row.payload["payload"]
    assert payload["payment_number"] == payment_number
    assert Decimal(payload["base_amount_paid"]) == Decimal("5200.0000")
    assert Decimal(payload["base_amount_cleared"]) == Decimal("5000.0000")
    assert Decimal(payload["fx_gain_loss_amount"]) == Decimal("200.0000")

    # 5. Process through Accounting GL Bridge consumer
    domain_event = DomainEvent(
        event_type="purchase.payment_made",
        payload=payload,
        event_id=event_row.payload.get("event_id", str(event_row.id)),
        tenant_id=str(event_row.tenant_id),
    )
    journal_entry = await handle_payment_made(domain_event, session=db_session)
    assert journal_entry is not None
    assert journal_entry.status == JournalEntryStatus.POSTED

    stmt_lines = select(TransactionLine).where(TransactionLine.journal_entry_id == journal_entry.id)
    res_lines = await db_session.execute(stmt_lines)
    lines = res_lines.scalars().all()
    assert len(lines) == 3

    ap_id = await get_default_account_id(db_session, AccountMappingKey.ACCOUNTS_PAYABLE)
    cash_id = await get_default_account_id(db_session, AccountMappingKey.CASH_AND_BANKS)
    fx_exp_id = await get_default_account_id(db_session, AccountMappingKey.FX_VARIANCE_EXPENSE)

    total_debit = Decimal("0.0000")
    total_credit = Decimal("0.0000")
    for line in lines:
        total_debit += line.debit
        total_credit += line.credit
        if line.account_id == ap_id:
            assert line.debit == Decimal("5000.0000")
            assert line.credit == Decimal("0.0000")
        elif line.account_id == cash_id:
            assert line.debit == Decimal("0.0000")
            assert line.credit == Decimal("5200.0000")
        elif line.account_id == fx_exp_id:
            # FX Loss debits expense account
            assert line.debit == Decimal("200.0000")
            assert line.credit == Decimal("0.0000")

    assert total_debit == total_credit == Decimal("5200.0000")

    # 6. Verify Idempotency
    dup_entry = await handle_payment_made(domain_event, session=db_session)
    assert dup_entry.id == journal_entry.id


@pytest.mark.asyncio
async def test_supplier_payment_fx_gain_and_gl_bridge(db_session: AsyncSession, seed_tenant_and_users):
    """
    Test Phase 4b Step 4: Supplier Payments with Realized FX Gain.
    1. Bill Date Rate C = 50.000000 for 100 USD -> Base AP Liability cleared = 5,000 EGP.
    2. Payment Date Rate D = 48.000000 for 100 USD -> Base Treasury Paid = 4,800 EGP.
    3. fx_gain_loss_amount = -200.0000 EGP (Realized FX Gain).
    4. Post payment -> check GL Bridge (DR AP 5000, CR Treasury 4800, CR FX Variance Expense 200).
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()
    treasury_id = uuid4()

    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "item_id": uuid4(),
                "qty_ordered": "10.0000",
                "unit_price": "10.0000",  # Total 100 USD
            }
        ],
        currency="USD",
    )
    await confirm_purchase_order(db_session, po.id)

    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po.id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "po_line_id": str(po.lines[0].id),
                "item_id": po.lines[0].item_id,
                "qty_received": "10.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=f"GRN-FXG-{uuid4().hex[:6]}",
    )

    bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-FXG-{uuid4().hex[:6]}",
        lines_data=[
            {
                "po_line_id": str(po.lines[0].id),
                "grn_line_id": str(grn.lines[0].id),
                "qty_billed": "10.0000",
                "unit_price": "10.0000",
            }
        ],
        currency="USD",
        fx_rate=Decimal("50.000000"),
    )
    await execute_three_way_match(db_session, bill.id)
    await post_vendor_bill(db_session, bill.id)

    payment_number = f"PAY-FXG-{uuid4().hex[:6]}"
    payment = await create_supplier_payment(
        session=db_session,
        supplier_id=supplier_id,
        treasury_id=treasury_id,
        payment_number=payment_number,
        amount=Decimal("100.0000"),
        currency="USD",
        fx_rate=Decimal("48.000000"),
    )

    payment = await allocate_payment(
        session=db_session,
        payment_id=payment.id,
        bill_id=bill.id,
        allocated_amount=Decimal("100.0000"),
    )
    # Base Paid = 100 * 48 = 4800; Base Cleared = 100 * 50 = 5000 -> FX Gain = -200.0000
    assert payment.fx_gain_loss_amount == Decimal("-200.0000")

    await post_supplier_payment(db_session, payment.id)

    stmt = select(OutboxEvent).where(OutboxEvent.event_type == "purchase.payment_made")
    res = await db_session.execute(stmt)
    event_row = res.scalars().all()[-1]

    domain_event = DomainEvent(
        event_type="purchase.payment_made",
        payload=event_row.payload["payload"],
        event_id=event_row.payload.get("event_id", str(event_row.id)),
        tenant_id=str(event_row.tenant_id),
    )
    journal_entry = await handle_payment_made(domain_event, session=db_session)
    assert journal_entry is not None

    stmt_lines = select(TransactionLine).where(TransactionLine.journal_entry_id == journal_entry.id)
    res_lines = await db_session.execute(stmt_lines)
    lines = res_lines.scalars().all()
    assert len(lines) == 3

    fx_exp_id = await get_default_account_id(db_session, AccountMappingKey.FX_VARIANCE_EXPENSE)
    total_debit = Decimal("0.0000")
    total_credit = Decimal("0.0000")
    for line in lines:
        total_debit += line.debit
        total_credit += line.credit
        if line.account_id == fx_exp_id:
            # FX Gain credits expense account
            assert line.debit == Decimal("0.0000")
            assert line.credit == Decimal("200.0000")

    assert total_debit == total_credit == Decimal("5000.0000")


@pytest.mark.asyncio
async def test_payment_allocation_validation_and_business_rules(db_session: AsyncSession, seed_tenant_and_users):
    """
    Test validation rules:
    1. Over-allocation beyond payment amount raises PaymentAllocationError.
    2. Allocating to an unposted bill raises ValueError.
    3. Allocating the same bill twice raises PaymentAllocationError.
    4. Allocating zero or negative amount raises PaymentAllocationError.
    """
    supplier_id = uuid4()
    treasury_id = uuid4()

    payment = await create_supplier_payment(
        session=db_session,
        supplier_id=supplier_id,
        treasury_id=treasury_id,
        payment_number=f"PAY-VAL-{uuid4().hex[:6]}",
        amount=Decimal("100.0000"),
    )

    # 1. Zero or negative allocation
    with pytest.raises(PaymentAllocationError, match="must be greater than zero"):
        await allocate_payment(db_session, payment.id, uuid4(), Decimal("0.0000"))

    # 2. Unposted bill allocation
    draft_bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-DRAFT-{uuid4().hex[:6]}",
        lines_data=[],
    )
    with pytest.raises(ValueError, match="expected 'POSTED'"):
        await allocate_payment(db_session, payment.id, draft_bill.id, Decimal("50.0000"))

    # Create and post a real bill for 50 EGP
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=uuid4(),
        lines_data=[{"item_id": uuid4(), "qty_ordered": "5.0000", "unit_price": "10.0000"}],
    )
    await confirm_purchase_order(db_session, po.id)
    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po.id,
        warehouse_id=po.warehouse_id,
        lines_data=[
            {
                "po_line_id": str(po.lines[0].id),
                "item_id": po.lines[0].item_id,
                "qty_received": "5.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=f"GRN-VAL-{uuid4().hex[:6]}",
    )
    valid_bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-VAL-{uuid4().hex[:6]}",
        lines_data=[
            {
                "po_line_id": str(po.lines[0].id),
                "grn_line_id": str(grn.lines[0].id),
                "qty_billed": "5.0000",
                "unit_price": "10.0000",
            }
        ],
    )
    await execute_three_way_match(db_session, valid_bill.id)
    await post_vendor_bill(db_session, valid_bill.id)

    # 3. Successful first allocation
    await allocate_payment(db_session, payment.id, valid_bill.id, Decimal("50.0000"))

    # 4. Duplicate allocation of the same bill
    with pytest.raises(PaymentAllocationError, match="is already allocated"):
        await allocate_payment(db_session, payment.id, valid_bill.id, Decimal("10.0000"))

    # 5. Over-allocation across multiple bills
    po2 = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=uuid4(),
        lines_data=[{"item_id": uuid4(), "qty_ordered": "10.0000", "unit_price": "10.0000"}],
    )
    await confirm_purchase_order(db_session, po2.id)
    grn2 = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po2.id,
        warehouse_id=po2.warehouse_id,
        lines_data=[
            {
                "po_line_id": str(po2.lines[0].id),
                "item_id": po2.lines[0].item_id,
                "qty_received": "10.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=f"GRN-VAL2-{uuid4().hex[:6]}",
    )
    bill2 = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-VAL2-{uuid4().hex[:6]}",
        lines_data=[
            {
                "po_line_id": str(po2.lines[0].id),
                "grn_line_id": str(grn2.lines[0].id),
                "qty_billed": "10.0000",
                "unit_price": "10.0000",
            }
        ],
    )
    await execute_three_way_match(db_session, bill2.id)
    await post_vendor_bill(db_session, bill2.id)

    # Allocating 60.0000 more when 50.0000 is already allocated on a 100.0000 payment -> total 110.0000
    with pytest.raises(PaymentAllocationError, match="exceeds payment amount"):
        await allocate_payment(db_session, payment.id, bill2.id, Decimal("60.0000"))


def test_alembic_payments_migration_structure():
    """
    Verify that the Phase 4b Step 4 Supplier Payments Alembic migration file can be loaded,
    has correct revision identifiers, and defines upgrade() and downgrade().
    """
    mig_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "tenant"
        / "versions"
        / "h8c3d4e5f6g7_phase_4b_step4_payments.py"
    )
    spec = importlib.util.spec_from_file_location("h8c3d4e5f6g7_phase_4b_step4_payments", mig_path)
    assert spec and spec.loader
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)

    assert getattr(mig_mod, "revision", None) == "h8c3d4e5f6g7"
    assert getattr(mig_mod, "down_revision", None) == "g7b2c3d4e5f6"
    assert callable(getattr(mig_mod, "upgrade", None))
    assert callable(getattr(mig_mod, "downgrade", None))
