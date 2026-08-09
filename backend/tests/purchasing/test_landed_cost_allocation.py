"""
tests/purchasing/test_landed_cost_allocation.py — Integration tests for Phase 4b Step 3

Covers:
  1. Largest Remainder Method exact piastre allocation (e.g. allocating 10,000 EGP across 3 equal items
     and 100 EGP across 7 equal items) results in ZERO fractional piastre drift.
  2. ImportShipment creation, content hashing (FR-1212), and landed cost allocation persistence.
  3. Updating GoodsReceiptLine.expected_landed_unit_cost based on allocations.
  4. Emission of purchase.landed_cost_allocated domain outbox event.
  5. Accounting GL Bridge consumer (handle_landed_cost_allocated):
     - DEBIT Inventory Asset
     - CREDIT Landed Cost Clearing
     - Validating idempotency on duplicate event processing.
  6. Alembic migration verification for Phase 4b Step 3.
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
from app.modules.accounting.consumers.purchasing_events import handle_landed_cost_allocated
from app.modules.accounting.models.core import (
    JournalEntry,
    JournalEntryLine as TransactionLine,
    JournalEntryStatus,
)
from app.modules.accounting.services.mappings import AccountMappingKey, get_default_account_id
from app.modules.purchasing.models.core import GoodsReceiptLine, GoodsReceiptStatus
from app.modules.purchasing.models.landed_cost import (
    AllocationBasis,
    ImportShipment,
    ImportShipmentStage,
    ImportShipmentStatus,
    LandedCostAllocation,
    LandedCostLine,
    LandedCostType,
)
from app.modules.purchasing.services.allocation import (
    allocate_shipment_costs,
    calculate_exact_allocations,
    create_import_shipment,
    post_landed_costs,
)
from app.modules.purchasing.services.orders import confirm_purchase_order, create_purchase_order
from app.modules.purchasing.services.receiving import receive_goods
from app.modules.system.models import OutboxEvent


def test_largest_remainder_math_exact_piastre_allocation():
    """
    Verify that calculate_exact_allocations uses the Largest Remainder Method (Hamilton method)
    to allocate tricky indivisible amounts without losing a single fractional piastre.
    """
    # Test case 1: 10,000 EGP across 3 equal items
    lines_3 = [
        GoodsReceiptLine(id=uuid4(), grn_id=uuid4(), item_id=uuid4(), qty_received=Decimal("10.0000"), unit_cost_estimated=Decimal("100.0000")),
        GoodsReceiptLine(id=uuid4(), grn_id=uuid4(), item_id=uuid4(), qty_received=Decimal("10.0000"), unit_cost_estimated=Decimal("100.0000")),
        GoodsReceiptLine(id=uuid4(), grn_id=uuid4(), item_id=uuid4(), qty_received=Decimal("10.0000"), unit_cost_estimated=Decimal("100.0000")),
    ]
    allocs_3 = calculate_exact_allocations(
        cost_line_amount=Decimal("10000.0000"),
        grn_lines=lines_3,
        allocation_basis=AllocationBasis.VALUE,
    )
    assert len(allocs_3) == 3
    # 10000 / 3 = 3333.3333 with 0.0001 residue
    assert allocs_3[0]["allocated_amount"] == Decimal("3333.3334")
    assert allocs_3[1]["allocated_amount"] == Decimal("3333.3333")
    assert allocs_3[2]["allocated_amount"] == Decimal("3333.3333")
    assert sum(a["allocated_amount"] for a in allocs_3) == Decimal("10000.0000")

    # Test case 2: 100 EGP across 7 equal items (100 / 7 = 14.285714...)
    lines_7 = [
        GoodsReceiptLine(id=uuid4(), grn_id=uuid4(), item_id=uuid4(), qty_received=Decimal("1.0000"), unit_cost_estimated=Decimal("10.0000"))
        for _ in range(7)
    ]
    allocs_7 = calculate_exact_allocations(
        cost_line_amount=Decimal("100.0000"),
        grn_lines=lines_7,
        allocation_basis=AllocationBasis.QTY,
    )
    assert len(allocs_7) == 7
    # 7 * 14.2857 = 99.9999, residue 0.0001 goes to first line
    assert allocs_7[0]["allocated_amount"] == Decimal("14.2858")
    for a in allocs_7[1:]:
        assert a["allocated_amount"] == Decimal("14.2857")
    assert sum(a["allocated_amount"] for a in allocs_7) == Decimal("100.0000")


@pytest.mark.asyncio
async def test_landed_cost_shipment_posting_and_gl_bridge(db_session: AsyncSession, seed_tenant_and_users):
    """
    Test full landed cost lifecycle:
      1. Create PO and GRN with 3 items of equal quantity.
      2. Create ImportShipment with 10,000.0000 EGP freight cost.
      3. Post Landed Costs -> allocates 10,000.0000 exactly across 3 items.
      4. Verify GoodsReceiptLine.expected_landed_unit_cost is updated.
      5. Verify purchase.landed_cost_allocated outbox event emission.
      6. Consume event via handle_landed_cost_allocated -> creates DR Inventory Asset / CR Landed Cost Clearing.
      7. Verify idempotency.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()

    # 1. Create PO for 3 equal items (10 units each @ 100 EGP)
    item_ids = [uuid4(), uuid4(), uuid4()]
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {"item_id": item_id, "qty_ordered": "10.0000", "unit_price": "100.0000"}
            for item_id in item_ids
        ],
        currency="EGP",
    )
    po_id = po.id
    po_line_ids = [str(line.id) for line in po.lines]
    await confirm_purchase_order(db_session, po_id)

    # 2. Receive Goods (GRN)
    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        po_id=po_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "po_line_id": po_line_ids[idx],
                "item_id": item_ids[idx],
                "qty_received": "10.0000",
                "qty_rejected": "0.0000",
            }
            for idx in range(3)
        ],
        grn_number=f"GRN-LC-{uuid4().hex[:6]}",
    )
    assert grn.status == GoodsReceiptStatus.POSTED
    grn_id = grn.id

    # 3. Create ImportShipment
    shipment_ref = f"SHP-10K-{uuid4().hex[:6]}"
    shipment = await create_import_shipment(
        session=db_session,
        shipment_ref=shipment_ref,
        supplier_ids=[supplier_id],
        po_ids=[po_id],
        currency="EGP",
        lines_data=[
            {
                "cost_type": LandedCostType.FREIGHT,
                "amount": "10000.0000",
                "allocation_basis": AllocationBasis.VALUE,
            }
        ],
    )
    assert shipment.status == ImportShipmentStatus.DRAFT
    assert shipment.total_landed_cost == Decimal("10000.0000")
    assert shipment.content_hash is not None
    shipment_id = shipment.id
    shipment_line_id = shipment.lines[0].id

    # 4. Post Landed Costs
    stmt_grn_lines_pre = select(GoodsReceiptLine).where(GoodsReceiptLine.grn_id == grn_id)
    res_grn_lines_pre = await db_session.execute(stmt_grn_lines_pre)
    grn_lines_for_post = list(res_grn_lines_pre.scalars().all())

    posted_shipment = await post_landed_costs(
        session=db_session,
        shipment_id=shipment_id,
        grn_lines=grn_lines_for_post,
    )
    assert posted_shipment.status == ImportShipmentStatus.POSTED
    assert posted_shipment.stage == ImportShipmentStage.CLEARED

    # 5. Verify DB allocations sum exactly to 10,000.0000
    stmt_alloc = select(LandedCostAllocation).where(
        LandedCostAllocation.landed_cost_line_id == shipment_line_id
    )
    res_alloc = await db_session.execute(stmt_alloc)
    allocations_db = res_alloc.scalars().all()
    assert len(allocations_db) == 3

    total_allocated_db = sum(a.allocated_amount for a in allocations_db)
    assert total_allocated_db == Decimal("10000.0000")

    # 6. Verify GoodsReceiptLine.expected_landed_unit_cost
    # Original unit_cost_estimated = 100.0000, allocated per item = 3333.3333/3333.3334
    # For 10 units: add-on per unit is 333.3333 / 333.3333 / 333.3333 -> expected ~ 433.3333
    stmt_grn_lines = select(GoodsReceiptLine).where(GoodsReceiptLine.grn_id == grn.id)
    res_grn_lines = await db_session.execute(stmt_grn_lines)
    grn_lines_db = res_grn_lines.scalars().all()
    for line in grn_lines_db:
        assert line.expected_landed_unit_cost is not None
        assert line.expected_landed_unit_cost >= Decimal("433.3333")

    # 7. Verify Outbox domain event emission
    stmt_ev = select(OutboxEvent).where(OutboxEvent.event_type == "purchase.landed_cost_allocated")
    res_ev = await db_session.execute(stmt_ev)
    outbox_events = res_ev.scalars().all()
    assert len(outbox_events) >= 1

    last_event = outbox_events[-1]
    payload = last_event.payload
    assert payload["payload"]["shipment_ref"] == shipment_ref
    assert payload["payload"]["total_landed_cost"] == "10000.0000"
    assert len(payload["payload"]["allocations"]) == 3

    # ── 8. Verify Accounting GL Bridge Consumer ──────────────────────────────
    domain_event = DomainEvent(
        event_type="purchase.landed_cost_allocated",
        tenant_id="system",
        payload=payload["payload"],
    )
    gl_journal = await handle_landed_cost_allocated(domain_event, session=db_session)
    assert gl_journal is not None
    assert gl_journal.reference == f"SHP-{shipment_ref}"
    assert gl_journal.status == JournalEntryStatus.POSTED

    stmt_lines = select(TransactionLine).where(TransactionLine.journal_entry_id == gl_journal.id)
    res_lines = await db_session.execute(stmt_lines)
    journal_lines = res_lines.scalars().all()
    assert len(journal_lines) == 2

    inv_id = await get_default_account_id(db_session, AccountMappingKey.INVENTORY_ASSET)
    clearing_id = await get_default_account_id(db_session, AccountMappingKey.LANDED_COST_CLEARING)

    dr_inv = next(line for line in journal_lines if line.account_id == inv_id)
    cr_clearing = next(line for line in journal_lines if line.account_id == clearing_id)
    assert dr_inv.debit == Decimal("10000.0000")
    assert cr_clearing.credit == Decimal("10000.0000")

    # 9. Verify Idempotency
    dup_journal = await handle_landed_cost_allocated(domain_event, session=db_session)
    assert dup_journal.id == gl_journal.id


def test_alembic_landed_cost_migration_structure():
    """
    Verify that the Phase 4b Step 3 Landed Cost Alembic migration file can be loaded,
    has correct revision identifiers, and defines upgrade() and downgrade().
    """
    mig_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "tenant"
        / "versions"
        / "g7b2c3d4e5f6_phase_4b_step3_landed_cost.py"
    )
    spec = importlib.util.spec_from_file_location("g7b2c3d4e5f6_phase_4b_step3_landed_cost", mig_path)
    assert spec and spec.loader
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)

    assert getattr(mig_mod, "revision", None) == "g7b2c3d4e5f6"
    assert getattr(mig_mod, "down_revision", None) == "f6a1b2c3d4e5"
    assert callable(getattr(mig_mod, "upgrade", None))
    assert callable(getattr(mig_mod, "downgrade", None))
