"""
tests/purchasing/test_purchasing_engine.py — Integration tests for Phase 4b Purchasing Module

Covers:
  1. PO Creation, DocumentLifecycleMixin state, and Phase 4a Approval Engine integration.
  2. The Golden Invariant (FR-522): qty_received <= qty_ordered (0% tolerance), raises OverReceiptError.
  3. Bounded Context event emission ('purchase.goods_received' Outbox event).
  4. Inventory Consumer execution: StockLevel increment, StockMovement audit trail, and CostLayer creation in Base Currency.
  5. Alembic migration verification for Phase 4b schema.
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
from app.core.models.mixins import DocumentState
from app.modules.approvals.models import DecisionType
from app.modules.approvals.services import decide_approval, submit_for_approval
from app.modules.inventory.consumers.purchasing_events import handle_goods_received
from app.modules.inventory.models.core import CostLayer, StockLevel, StockMovement
from app.modules.purchasing.exceptions import OverReceiptError
from app.modules.purchasing.models.core import (
    GoodsReceipt,
    GoodsReceiptStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
)
from app.modules.purchasing.services.orders import confirm_purchase_order, create_purchase_order
from app.modules.purchasing.services.receiving import receive_goods
from app.modules.system.models import OutboxEvent


@pytest.mark.asyncio
async def test_po_creation_and_approval_engine_integration(db_session: AsyncSession):
    """
    Test that a PurchaseOrder inherits DocumentLifecycleMixin, computes a deterministic
    content_hash, and integrates seamlessly with the Phase 4a approval engine.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()
    user_submitter = uuid4()
    user_approver = uuid4()

    lines_data = [
        {
            "item_id": uuid4(),
            "qty_ordered": "100.0000",
            "unit_price": "10.0000",
        },
        {
            "item_id": uuid4(),
            "qty_ordered": "50.0000",
            "unit_price": "20.0000",
        },
    ]

    # 1. Create PO
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=lines_data,
        currency="EGP",
        fx_rate="1.0000",
    )

    assert po.status == PurchaseOrderStatus.DRAFT
    assert po.state == DocumentState.DRAFT
    assert po.total_amount == Decimal("2000.0000")
    assert po.content_hash is not None
    assert len(po.lines) == 2

    # 2. Submit for Approval via Phase 4a engine
    approvable_content = {
        "po_number": po.po_number,
        "supplier_id": str(po.supplier_id),
        "warehouse_id": str(po.warehouse_id),
        "currency": po.currency,
        "fx_rate": str(po.fx_rate),
        "total_amount": str(po.total_amount),
        "lines": [
            {
                "item_id": str(line.item_id),
                "variant_id": str(line.variant_id) if line.variant_id else None,
                "qty_ordered": str(line.qty_ordered),
                "unit_price": str(line.unit_price),
            }
            for line in po.lines
        ],
    }

    req = await submit_for_approval(
        session=db_session,
        document_type="purchase_order",
        document_id=po.id,
        document=po,
        requested_by=user_submitter,
        approvable_content=approvable_content,
    )
    assert po.state == DocumentState.PENDING_APPROVAL

    # 3. Approve via Phase 4a engine (Segregation of Duties observed: approver != submitter)
    await decide_approval(
        session=db_session,
        approval_request_id=req.id,
        decision=DecisionType.APPROVE,
        decided_by=user_approver,
        document=po,
    )
    assert po.state == DocumentState.APPROVED

    # 4. Confirm PO
    confirmed_po = await confirm_purchase_order(db_session, po.id)
    assert confirmed_po.status == PurchaseOrderStatus.CONFIRMED


@pytest.mark.asyncio
async def test_golden_invariant_over_receipt_raises_error(db_session: AsyncSession):
    """
    Test FR-522: The Golden Invariant mathematically enforces qty_received <= qty_ordered
    for every line with 0% tolerance. Attempts to over-receive raise OverReceiptError.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()
    item_id = uuid4()

    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        lines_data=[
            {
                "item_id": item_id,
                "qty_ordered": "10.0000",
                "unit_price": "50.0000",
            }
        ],
    )
    await confirm_purchase_order(db_session, po.id)

    # First receipt of 6.0000 -> succeeds
    grn1 = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        po_id=po.id,
        lines_data=[
            {
                "po_line_id": po.lines[0].id,
                "item_id": item_id,
                "qty_received": "6.0000",
            }
        ],
    )
    assert grn1.status == GoodsReceiptStatus.POSTED
    assert po.lines[0].qty_received == Decimal("6.0000")
    assert po.status == PurchaseOrderStatus.PARTIALLY_RECEIVED

    # Attempt second receipt of 5.0000 (total would be 11.0000 > 10.0000) -> raises OverReceiptError
    with pytest.raises(OverReceiptError) as exc_info:
        await receive_goods(
            session=db_session,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            po_id=po.id,
            lines_data=[
                {
                    "po_line_id": po.lines[0].id,
                    "item_id": item_id,
                    "qty_received": "5.0000",
                }
            ],
        )

    assert "exceeds ordered quantity" in str(exc_info.value)
    # Ensure qty_received remained unchanged at 6.0000
    assert po.lines[0].qty_received == Decimal("6.0000")


@pytest.mark.asyncio
async def test_grn_emits_outbox_event_and_creates_cost_layer(db_session: AsyncSession):
    """
    Test Bounded Context architecture:
      1. receive_goods emits 'purchase.goods_received' Outbox event without touching StockLevel or CostLayer.
      2. Inventory consumer handle_goods_received processes the event:
           - Increments StockLevel quantity.
           - Records StockMovement audit trail.
           - Creates new CostLayer using Base Currency unit cost (FR-520).
      3. Verifies idempotency when consumer processes the same event again.
    """
    supplier_id = uuid4()
    warehouse_id = uuid4()
    item_id = uuid4()

    # Create PO in USD with FX rate = 50.0000 EGP per USD
    po = await create_purchase_order(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        currency="USD",
        fx_rate="50.0000",
        lines_data=[
            {
                "item_id": item_id,
                "qty_ordered": "10.0000",
                "unit_price": "20.0000",  # 20.0000 USD -> 1000.0000 EGP base currency cost
            }
        ],
    )
    await confirm_purchase_order(db_session, po.id)

    # Execute receipt of full 10.0000 units
    grn = await receive_goods(
        session=db_session,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        po_id=po.id,
        lines_data=[
            {
                "po_line_id": po.lines[0].id,
                "item_id": item_id,
                "qty_received": "10.0000",
            }
        ],
    )
    assert po.status == PurchaseOrderStatus.RECEIVED

    # 1. Verify OutboxEvent was published
    stmt_outbox = select(OutboxEvent).where(OutboxEvent.event_type == "purchase.goods_received")
    res_outbox = await db_session.execute(stmt_outbox)
    outbox_event = res_outbox.scalar_one()

    assert outbox_event.event_type == "purchase.goods_received"
    domain_event_data = outbox_event.payload
    payload = domain_event_data["payload"]
    assert payload["grn_id"] == str(grn.id)
    assert Decimal(payload["fx_rate"]) == Decimal("50.0000")
    assert len(payload["lines"]) == 1
    assert Decimal(payload["lines"][0]["unit_cost_base"]) == Decimal("1000.0000")  # 20.0000 * 50.0000

    # 2. Execute Inventory Event Consumer (The GL/Inventory Bridge)
    domain_event = DomainEvent(**domain_event_data)
    created_layers = await handle_goods_received(domain_event, session=db_session)

    assert len(created_layers) == 1
    layer = created_layers[0]
    assert layer.item_id == item_id
    assert layer.warehouse_id == warehouse_id
    assert layer.qty_received == Decimal("10.0000")
    assert layer.qty_remaining == Decimal("10.0000")
    assert layer.unit_cost_original == Decimal("1000.0000")  # Verified Base Currency cost
    assert layer.unit_cost_current == Decimal("1000.0000")

    # Verify physical StockLevel increment
    stmt_level = select(StockLevel).where(
        StockLevel.item_id == item_id,
        StockLevel.warehouse_id == warehouse_id,
    )
    res_level = await db_session.execute(stmt_level)
    stock_level = res_level.scalar_one()
    assert stock_level.quantity == Decimal("10.0000")

    # Verify StockMovement audit trail
    stmt_movement = select(StockMovement).where(
        StockMovement.reference_id == str(grn.id),
        StockMovement.movement_type == "PURCHASE_RECEIPT",
    )
    res_movement = await db_session.execute(stmt_movement)
    movement = res_movement.scalar_one()
    assert movement.qty == Decimal("10.0000")
    assert movement.item_id == item_id

    # 3. Test Idempotency: re-running handle_goods_received should skip processing
    duplicate_layers = await handle_goods_received(domain_event, session=db_session)
    assert len(duplicate_layers) == 0  # Idempotently skipped


def test_alembic_migration_structure():
    """
    Verify Alembic migration e5f6a1b2c3d4_phase_4b_purchasing.py conforms to
    upgrade/downgrade structure and revision dependency chain.
    """
    mig_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "tenant"
        / "versions"
        / "e5f6a1b2c3d4_phase_4b_purchasing.py"
    )
    spec = importlib.util.spec_from_file_location("e5f6a1b2c3d4_phase_4b_purchasing", mig_path)
    assert spec and spec.loader
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)

    assert getattr(mig_mod, "revision", None) == "e5f6a1b2c3d4"
    assert getattr(mig_mod, "down_revision", None) == "d4e5f6a1b2c3"
    assert callable(getattr(mig_mod, "upgrade", None))
    assert callable(getattr(mig_mod, "downgrade", None))
