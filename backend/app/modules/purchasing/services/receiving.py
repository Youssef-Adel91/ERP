"""
app/modules/purchasing/services/receiving.py — Goods Receipt (GRN) Service

Enforces:
  1. Golden Invariant (FR-522): qty_received <= qty_ordered (0% tolerance), raises OverReceiptError.
  2. Bounded Context: Emits 'purchase.goods_received' Outbox event without touching StockLevel or CostLayer.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.models.mixins import DocumentState
from app.modules.purchasing.exceptions import OverReceiptError, PurchaseOrderNotFoundError
from app.modules.purchasing.models.core import (
    GoodsReceipt,
    GoodsReceiptLine,
    GoodsReceiptStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
)


async def receive_goods(
    session: AsyncSession,
    supplier_id: UUID | str,
    warehouse_id: UUID | str,
    lines_data: list[dict],
    po_id: UUID | str | None = None,
    receipt_date: date | None = None,
    branch_id: UUID | str | None = None,
    supplier_delivery_ref: str | None = None,
    grn_number: str | None = None,
) -> GoodsReceipt:
    """
    Records an inbound GoodsReceipt (GRN).
    Enforces qty_received <= qty_ordered invariant (FR-522).
    Emits purchase.goods_received domain event to the Outbox for Inventory processing.
    """
    if not lines_data:
        raise ValueError("GoodsReceipt must contain at least one line")

    if isinstance(supplier_id, str):
        supplier_id = UUID(supplier_id)
    if isinstance(warehouse_id, str):
        warehouse_id = UUID(warehouse_id)
    if isinstance(po_id, str) and po_id:
        po_id = UUID(po_id)
    if isinstance(branch_id, str) and branch_id:
        branch_id = UUID(branch_id)

    if not grn_number:
        grn_number = f"GRN-{uuid4().hex[:8].upper()}"

    po: PurchaseOrder | None = None
    po_lines_by_id = {}
    po_lines_by_item = {}

    if po_id:
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(selectinload(PurchaseOrder.lines))
            .with_for_update()
        )
        res = await session.execute(stmt)
        po = res.scalar_one_or_none()
        if not po:
            raise PurchaseOrderNotFoundError(po_id)
        for po_line in po.lines:
            po_lines_by_id[po_line.id] = po_line
            po_lines_by_item[(po_line.item_id, po_line.variant_id)] = po_line

    grn = GoodsReceipt(
        po_id=po.id if po else None,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        branch_id=branch_id,
        grn_number=grn_number,
        receipt_date=receipt_date or date.today(),
        supplier_delivery_ref=supplier_delivery_ref,
        status=GoodsReceiptStatus.POSTED,
        state=DocumentState.POSTED,
    )
    session.add(grn)
    await session.flush()

    created_grn_lines = []
    for line_dict in lines_data:
        item_id = line_dict["item_id"]
        if isinstance(item_id, str):
            item_id = UUID(item_id)
        variant_id = line_dict.get("variant_id")
        if isinstance(variant_id, str) and variant_id:
            variant_id = UUID(variant_id)

        qty_received = Decimal(str(line_dict["qty_received"]))
        qty_rejected = Decimal(str(line_dict.get("qty_rejected", "0.0000")))
        batch_id = line_dict.get("batch_id")
        if isinstance(batch_id, str) and batch_id:
            batch_id = UUID(batch_id)
        serial_ids = line_dict.get("serial_ids") or []

        po_line_id = line_dict.get("po_line_id")
        if isinstance(po_line_id, str) and po_line_id:
            po_line_id = UUID(po_line_id)

        po_line = None
        if po_line_id and po_line_id in po_lines_by_id:
            po_line = po_lines_by_id[po_line_id]
        elif po and (item_id, variant_id) in po_lines_by_item:
            po_line = po_lines_by_item[(item_id, variant_id)]

        # Golden Invariant (FR-522): Mathematically enforce qty_received <= qty_ordered
        if po_line:
            new_received = po_line.qty_received + qty_received
            if new_received > po_line.qty_ordered:
                raise OverReceiptError(
                    po_line_id=po_line.id,
                    qty_ordered=str(po_line.qty_ordered),
                    current_received=str(po_line.qty_received),
                    attempted_receipt=str(qty_received),
                )
            po_line.qty_received = new_received
            session.add(po_line)

            unit_cost_est = (
                Decimal(str(line_dict["unit_cost_estimated"]))
                if line_dict.get("unit_cost_estimated") is not None
                else (po_line.expected_landed_unit_cost or po_line.unit_price)
            )
        else:
            unit_cost_est = Decimal(str(line_dict.get("unit_cost_estimated", "0.0000")))

        grn_line = GoodsReceiptLine(
            grn_id=grn.id,
            po_line_id=po_line.id if po_line else None,
            item_id=item_id,
            variant_id=variant_id,
            qty_received=qty_received,
            qty_rejected=qty_rejected,
            batch_id=batch_id,
            serial_ids=serial_ids,
            unit_cost_estimated=unit_cost_est,
        )
        session.add(grn_line)
        created_grn_lines.append(grn_line)

    await session.flush()

    if po:
        if all(line.qty_received >= line.qty_ordered for line in po.lines):
            po.status = PurchaseOrderStatus.RECEIVED
        elif any(line.qty_received > 0 for line in po.lines):
            po.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
        session.add(po)

    # ── Emit purchase.goods_received domain event via Transactional Outbox ────
    try:
        from app.core.db.context import current_tenant

        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        tenant_id = "system"

    fx_rate = po.fx_rate if po else Decimal("1.0000")
    lines_payload = []
    for g_line in created_grn_lines:
        # Calculate Base Currency unit cost (FR-520 / Bounded Context requirement)
        unit_cost_base = g_line.unit_cost_estimated * fx_rate
        lines_payload.append(
            {
                "grn_line_id": str(g_line.id),
                "po_line_id": str(g_line.po_line_id) if g_line.po_line_id else None,
                "item_id": str(g_line.item_id),
                "variant_id": str(g_line.variant_id) if g_line.variant_id else None,
                "qty_received": str(g_line.qty_received),
                "qty_rejected": str(g_line.qty_rejected),
                "batch_id": str(g_line.batch_id) if g_line.batch_id else None,
                "serial_ids": g_line.serial_ids or [],
                "unit_cost_base": str(unit_cost_base),
                "unit_cost_estimated": str(g_line.unit_cost_estimated),
            }
        )

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="purchase.goods_received",
        tenant_id=str(tenant_id),
        payload={
            "grn_id": str(grn.id),
            "po_id": str(po.id) if po else None,
            "supplier_id": str(grn.supplier_id),
            "warehouse_id": str(grn.warehouse_id),
            "branch_id": str(grn.branch_id) if grn.branch_id else None,
            "receipt_date": grn.receipt_date.isoformat(),
            "grn_number": grn.grn_number,
            "currency": po.currency if po else "EGP",
            "fx_rate": str(fx_rate),
            "lines": lines_payload,
        },
    )
    await event_bus.publish(event, session=session)

    # Reload with lines relationship populated
    stmt = (
        select(GoodsReceipt)
        .where(GoodsReceipt.id == grn.id)
        .options(selectinload(GoodsReceipt.lines))
    )
    res = await session.execute(stmt)
    return res.scalar_one()
