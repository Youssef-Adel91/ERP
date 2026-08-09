"""
app/modules/purchasing/services/orders.py — Purchase Order Lifecycle Services
"""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.models.mixins import DocumentState
from app.modules.purchasing.exceptions import InvalidPOStateError, PurchaseOrderNotFoundError
from app.modules.purchasing.models.core import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
)


async def create_purchase_order(
    session: AsyncSession,
    supplier_id: UUID | str,
    warehouse_id: UUID | str,
    lines_data: list[dict],
    order_date: date | None = None,
    expected_date: date | None = None,
    currency: str = "EGP",
    fx_rate: Decimal | str = Decimal("1.0000"),
    branch_id: UUID | str | None = None,
    po_number: str | None = None,
) -> PurchaseOrder:
    """
    Creates a new PurchaseOrder in DRAFT status with lifecycle state DRAFT.
    Calculates total_amount and initializes SHA-256 approvable content_hash.
    """
    if not lines_data:
        raise ValueError("PurchaseOrder must contain at least one line")

    if isinstance(supplier_id, str):
        supplier_id = UUID(supplier_id)
    if isinstance(warehouse_id, str):
        warehouse_id = UUID(warehouse_id)
    if isinstance(branch_id, str) and branch_id:
        branch_id = UUID(branch_id)
    if isinstance(fx_rate, str):
        fx_rate = Decimal(fx_rate)

    if not po_number:
        po_number = f"PO-{uuid4().hex[:8].upper()}"

    po = PurchaseOrder(
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        branch_id=branch_id,
        po_number=po_number,
        status=PurchaseOrderStatus.DRAFT,
        state=DocumentState.DRAFT,
        order_date=order_date or date.today(),
        expected_date=expected_date,
        currency=currency,
        fx_rate=fx_rate,
        total_amount=Decimal("0.0000"),
    )
    session.add(po)
    await session.flush()

    total_amount = Decimal("0.0000")
    approvable_lines = []

    for line_dict in lines_data:
        item_id = line_dict["item_id"]
        if isinstance(item_id, str):
            item_id = UUID(item_id)
        variant_id = line_dict.get("variant_id")
        if isinstance(variant_id, str) and variant_id:
            variant_id = UUID(variant_id)

        qty_ordered = Decimal(str(line_dict["qty_ordered"]))
        unit_price = Decimal(str(line_dict["unit_price"]))
        expected_landed = line_dict.get("expected_landed_unit_cost")
        if expected_landed is not None:
            expected_landed = Decimal(str(expected_landed))
        else:
            expected_landed = unit_price

        line_total = qty_ordered * unit_price
        total_amount += line_total

        line = PurchaseOrderLine(
            po_id=po.id,
            item_id=item_id,
            variant_id=variant_id,
            qty_ordered=qty_ordered,
            qty_received=Decimal("0.0000"),
            qty_billed=Decimal("0.0000"),
            unit_price=unit_price,
            expected_landed_unit_cost=expected_landed,
        )
        session.add(line)

        approvable_lines.append(
            {
                "item_id": str(item_id),
                "variant_id": str(variant_id) if variant_id else None,
                "qty_ordered": str(qty_ordered),
                "unit_price": str(unit_price),
            }
        )

    po.total_amount = total_amount

    # Compute deterministic SHA-256 approvable content hash (FR-1212)
    approvable_content = {
        "po_number": po.po_number,
        "supplier_id": str(po.supplier_id),
        "warehouse_id": str(po.warehouse_id),
        "currency": po.currency,
        "fx_rate": str(po.fx_rate),
        "total_amount": str(po.total_amount),
        "lines": approvable_lines,
    }
    po.content_hash = po.compute_approvable_content_hash(approvable_content)

    session.add(po)
    await session.flush()
    await session.refresh(po)

    # Reload with lines relationship populated
    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.id == po.id)
        .options(selectinload(PurchaseOrder.lines))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def confirm_purchase_order(
    session: AsyncSession,
    po_id: UUID | str,
) -> PurchaseOrder:
    """
    Transitions a PurchaseOrder from DRAFT or APPROVED state to CONFIRMED.
    """
    if isinstance(po_id, str):
        po_id = UUID(po_id)

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

    if po.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.CONFIRMED):
        raise InvalidPOStateError(po.id, str(po.status), "confirm")

    po.status = PurchaseOrderStatus.CONFIRMED
    if po.state == DocumentState.DRAFT:
        po.state = DocumentState.APPROVED

    session.add(po)
    await session.flush()
    await session.refresh(po)
    return po
