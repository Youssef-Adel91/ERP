"""
tests/purchasing/test_billing_and_three_way_match.py — Integration tests for Phase 4b Step 2

Covers:
  1. Three-Way Match quantity variance (FR-521, FR-527): attempting to bill for more quantity than received
     raises ThreeWayMatchError and transitions match_state to VARIANCE_BLOCKED.
  2. Three-Way Match price variance: attempting to bill with a price mismatch raises ThreeWayMatchError.
  3. Successful Three-Way Match: transitions match_state to MATCHED, creates ThreeWayMatchResult audit row,
     and updates PurchaseOrder status.
  4. VendorBill posting: transitions status to POSTED and emits purchase.bill_posted outbox event.
  5. Accounting GL Consumers (The GL Bridge):
     - handle_grn_posted creates DR Inventory Asset / CR GRNI Accrual
     - handle_bill_posted creates DR GRNI Accrual / CR Accounts Payable (clearing the GRNI liability)
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
from app.modules.accounting.consumers.purchasing_events import (
    handle_bill_posted,
    handle_grn_posted,
)
from app.modules.accounting.models.core import (
    JournalEntry,
    JournalEntryLine as TransactionLine,
    JournalEntryStatus,
)
from app.modules.accounting.services.mappings import AccountMappingKey, get_default_account_id
from app.modules.purchasing.exceptions import ThreeWayMatchError
from app.modules.purchasing.models.billing import (
    ThreeWayMatchResult,
    VendorBill,
    VendorBillMatchState,
    VendorBillStatus,
)
from app.modules.purchasing.models.core import GoodsReceipt
from app.modules.purchasing.services.billing import (
    create_vendor_bill,
    execute_three_way_match,
    post_vendor_bill,
)
from app.modules.purchasing.services.orders import confirm_purchase_order, create_purchase_order
from app.modules.purchasing.services.receiving import receive_goods
from app.modules.system.models import OutboxEvent


@pytest.mark.asyncio
async def test_three_way_match_over_billing_raises_error(db_session: AsyncSession):
    """
    Test that attempting to bill for more quantity than was received raises ThreeWayMatchError
    and blocks the bill with VARIANCE_BLOCKED match_state.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()

    # 1. Create PO for 100 units @ 10.00
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "item_id": uuid4(),
                "qty_ordered": "100.0000",
                "unit_price": "10.0000",
            }
        ],
        currency="EGP",
    )
    await confirm_purchase_order(db_session, po.id)
    po_line = po.lines[0]

    # 2. Receive GRN for 80 units
    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po.id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "item_id": po_line.item_id,
                "qty_received": "80.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=f"GRN-TEST-{uuid4().hex[:6]}",
    )
    grn_line = grn.lines[0]

    # 3. Attempt to bill for 90 units (qty_billed > qty_received)
    bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-OVR-{uuid4().hex[:6]}",
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "grn_line_id": str(grn_line.id),
                "qty_billed": "90.0000",
                "unit_price": "10.0000",
            }
        ],
    )

    # 4. Execute Three-Way Match -> should raise ThreeWayMatchError
    with pytest.raises(ThreeWayMatchError) as exc_info:
        await execute_three_way_match(session=db_session, bill_id=bill.id)

    assert "ThreeWayMatchError" in str(exc_info.value)
    assert Decimal(str(exc_info.value.qty_variance)) == Decimal("10.0000")

    # Verify match_state updated in DB
    await db_session.refresh(bill)
    assert bill.match_state == VendorBillMatchState.VARIANCE_BLOCKED

    # Verify immutable audit result row created
    stmt = select(ThreeWayMatchResult).where(ThreeWayMatchResult.bill_id == bill.id)
    res = await db_session.execute(stmt)
    results = res.scalars().all()
    assert len(results) == 1
    assert results[0].is_within_tolerance is False
    assert results[0].qty_variance == Decimal("10.0000")


@pytest.mark.asyncio
async def test_three_way_match_price_variance_raises_error(db_session: AsyncSession):
    """
    Test that attempting to bill at a higher unit price than PO raises ThreeWayMatchError.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()

    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "item_id": uuid4(),
                "qty_ordered": "100.0000",
                "unit_price": "10.0000",
            }
        ],
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
                "qty_received": "100.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=f"GRN-PRC-{uuid4().hex[:6]}",
    )
    grn_line = grn.lines[0]

    bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=f"BILL-PRC-{uuid4().hex[:6]}",
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "grn_line_id": str(grn_line.id),
                "qty_billed": "100.0000",
                "unit_price": "12.0000",  # Variance!
            }
        ],
    )

    with pytest.raises(ThreeWayMatchError) as exc_info:
        await execute_three_way_match(session=db_session, bill_id=bill.id)

    assert Decimal(str(exc_info.value.price_variance)) == Decimal("2.0000")
    await db_session.refresh(bill)
    assert bill.match_state == VendorBillMatchState.VARIANCE_BLOCKED


@pytest.mark.asyncio
async def test_three_way_match_success_and_gl_posting(db_session: AsyncSession, seed_tenant_and_users):
    """
    Test a complete, successful cycle:
      1. PO created -> GRN received -> Bill created matching exactly.
      2. Three-Way Match succeeds (MATCHED).
      3. Bill is posted -> emits purchase.bill_posted outbox event.
      4. GL Bridge Consumers process purchase.goods_received and purchase.bill_posted,
         verifying GRNI liability accrual and subsequent clearing to Accounts Payable.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()

    # 1. Create PO for 80 units @ 15.00 (= 1200.00 total)
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "item_id": uuid4(),
                "qty_ordered": "80.0000",
                "unit_price": "15.0000",
            }
        ],
        currency="EGP",
    )
    await confirm_purchase_order(db_session, po.id)
    po_line = po.lines[0]

    # 2. Receive GRN for 80 units
    grn_number = f"GRN-GL-{uuid4().hex[:6]}"
    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po.id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "item_id": po_line.item_id,
                "qty_received": "80.0000",
                "qty_rejected": "0.0000",
            }
        ],
        grn_number=grn_number,
    )
    grn_line = grn.lines[0]

    # Verify outbox event for goods receipt
    stmt = select(OutboxEvent).where(OutboxEvent.event_type == "purchase.goods_received")
    res = await db_session.execute(stmt)
    grn_outbox_events = res.scalars().all()
    assert len(grn_outbox_events) >= 1
    grn_event_payload = grn_outbox_events[-1].payload

    # 3. Create matching Vendor Bill
    bill_number = f"BILL-GL-{uuid4().hex[:6]}"
    bill = await create_vendor_bill(
        session=db_session,
        supplier_id=supplier_id,
        bill_number=bill_number,
        lines_data=[
            {
                "po_line_id": str(po_line.id),
                "grn_line_id": str(grn_line.id),
                "qty_billed": "80.0000",
                "unit_price": "15.0000",
            }
        ],
    )

    # 4. Execute Three-Way Match -> should succeed
    matched_bill = await execute_three_way_match(session=db_session, bill_id=bill.id)
    assert matched_bill.match_state == VendorBillMatchState.MATCHED

    # Verify audit log row
    stmt_res = select(ThreeWayMatchResult).where(ThreeWayMatchResult.bill_id == bill.id)
    res = await db_session.execute(stmt_res)
    match_rows = res.scalars().all()
    assert len(match_rows) == 1
    assert match_rows[0].is_within_tolerance is True

    # 5. Post Vendor Bill -> should succeed and publish purchase.bill_posted
    posted_bill = await post_vendor_bill(session=db_session, bill_id=bill.id)
    assert posted_bill.status == VendorBillStatus.POSTED

    stmt = select(OutboxEvent).where(OutboxEvent.event_type == "purchase.bill_posted")
    res = await db_session.execute(stmt)
    bill_outbox_events = res.scalars().all()
    assert len(bill_outbox_events) >= 1
    bill_event_payload = bill_outbox_events[-1].payload

    # ── 6. Verify GL Bridge Consumers ─────────────────────────────────────────

    # (A) Consume GRN outbox event -> creates DR Inventory / CR GRNI Accrual
    grn_domain_event = DomainEvent(
        event_type="purchase.goods_received",
        tenant_id="system",
        payload=grn_event_payload["payload"],
    )
    grn_journal = await handle_grn_posted(grn_domain_event, session=db_session)
    assert grn_journal is not None
    assert grn_journal.reference == f"GRN-{grn_number}"
    assert grn_journal.status == JournalEntryStatus.POSTED

    stmt_lines = select(TransactionLine).where(TransactionLine.journal_entry_id == grn_journal.id)
    res = await db_session.execute(stmt_lines)
    grn_lines = res.scalars().all()
    assert len(grn_lines) == 2

    inv_id = await get_default_account_id(db_session, AccountMappingKey.INVENTORY_ASSET)
    grni_id = await get_default_account_id(db_session, AccountMappingKey.GRNI_ACCRUAL)
    ap_id = await get_default_account_id(db_session, AccountMappingKey.ACCOUNTS_PAYABLE)

    dr_inv = next(line for line in grn_lines if line.account_id == inv_id)
    cr_grni = next(line for line in grn_lines if line.account_id == grni_id)
    assert dr_inv.debit == Decimal("1200.0000")
    assert cr_grni.credit == Decimal("1200.0000")

    # (B) Consume Bill outbox event -> creates DR GRNI Accrual / CR Accounts Payable
    bill_domain_event = DomainEvent(
        event_type="purchase.bill_posted",
        tenant_id="system",
        payload=bill_event_payload["payload"],
    )
    bill_journal = await handle_bill_posted(bill_domain_event, session=db_session)
    assert bill_journal is not None
    assert bill_journal.reference == f"BILL-{bill_number}"
    assert bill_journal.status == JournalEntryStatus.POSTED

    stmt_lines = select(TransactionLine).where(TransactionLine.journal_entry_id == bill_journal.id)
    res = await db_session.execute(stmt_lines)
    bill_lines = res.scalars().all()
    assert len(bill_lines) == 2

    dr_grni = next(line for line in bill_lines if line.account_id == grni_id)
    cr_ap = next(line for line in bill_lines if line.account_id == ap_id)
    assert dr_grni.debit == Decimal("1200.0000")
    assert cr_ap.credit == Decimal("1200.0000")

    # Idempotency verification
    duplicate_journal = await handle_bill_posted(bill_domain_event, session=db_session)
    assert duplicate_journal.id == bill_journal.id


def test_alembic_billing_migration_structure():
    """
    Verify that the Phase 4b Step 2 Billing Alembic migration file can be loaded,
    has correct revision identifiers, and defines upgrade() and downgrade().
    """
    mig_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "tenant"
        / "versions"
        / "f6a1b2c3d4e5_phase_4b_step2_billing.py"
    )
    spec = importlib.util.spec_from_file_location("f6a1b2c3d4e5_phase_4b_step2_billing", mig_path)
    assert spec and spec.loader
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)

    assert getattr(mig_mod, "revision", None) == "f6a1b2c3d4e5"
    assert getattr(mig_mod, "down_revision", None) == "e5f6a1b2c3d4"
    assert callable(getattr(mig_mod, "upgrade", None))
    assert callable(getattr(mig_mod, "downgrade", None))
