"""
app/modules/purchasing/services/billing.py — Vendor Bills & Three-Way Match Service

Implements:
  1. create_vendor_bill: Drafts a VendorBill with deterministic SHA-256 hash.
  2. execute_three_way_match: Enforces strict 0% tolerance Three-Way Match (FR-521, FR-527)
     against linked GoodsReceiptLine and PurchaseOrderLine.
  3. post_vendor_bill: Requires MATCHED state, posts bill, and publishes outbox event purchase.bill_posted.
"""
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.models.mixins import DocumentState
from app.modules.purchasing.exceptions import (
    ThreeWayMatchError,
    VendorBillNotFoundError,
)
from app.modules.purchasing.models.billing import (
    ThreeWayMatchResult,
    VendorBill,
    VendorBillLine,
    VendorBillMatchState,
    VendorBillStatus,
)
from app.modules.purchasing.models.core import (
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
)


async def create_vendor_bill(
    session: AsyncSession,
    supplier_id: UUID | str,
    bill_number: str,
    lines_data: list[dict[str, Any]],
    bill_date: date | None = None,
    due_date: date | None = None,
    currency: str = "EGP",
    fx_rate: Decimal | str = Decimal("1.000000"),
    branch_id: UUID | str | None = None,
    tax_total: Decimal | str = Decimal("0.0000"),
) -> VendorBill:
    """
    Create a new draft VendorBill with line items and deterministic SHA-256 content hash.
    """
    if isinstance(supplier_id, str):
        supplier_id = UUID(supplier_id)
    if isinstance(branch_id, str) and branch_id:
        branch_id = UUID(branch_id)
    if isinstance(fx_rate, str):
        fx_rate = Decimal(fx_rate)
    if isinstance(tax_total, str):
        tax_total = Decimal(tax_total)

    bill = VendorBill(
        supplier_id=supplier_id,
        bill_number=bill_number,
        bill_date=bill_date or date.today(),
        due_date=due_date or date.today(),
        currency=currency,
        fx_rate=fx_rate,
        branch_id=branch_id,
        match_state=VendorBillMatchState.UNMATCHED,
        status=VendorBillStatus.DRAFT,
        state=DocumentState.DRAFT,
        subtotal=Decimal("0.0000"),
        tax_total=tax_total,
        total_amount=Decimal("0.0000"),
    )
    session.add(bill)
    await session.flush()

    subtotal = Decimal("0.0000")
    approvable_lines = []

    for line_dict in lines_data:
        po_line_id = line_dict.get("po_line_id")
        if isinstance(po_line_id, str) and po_line_id:
            po_line_id = UUID(po_line_id)
        grn_line_id = line_dict.get("grn_line_id")
        if isinstance(grn_line_id, str) and grn_line_id:
            grn_line_id = UUID(grn_line_id)
        tax_code_id = line_dict.get("tax_code_id")
        if isinstance(tax_code_id, str) and tax_code_id:
            tax_code_id = UUID(tax_code_id)

        qty_billed = Decimal(str(line_dict["qty_billed"]))
        unit_price = Decimal(str(line_dict["unit_price"]))

        line_subtotal = qty_billed * unit_price
        subtotal += line_subtotal

        bill_line = VendorBillLine(
            bill_id=bill.id,
            po_line_id=po_line_id,
            grn_line_id=grn_line_id,
            qty_billed=qty_billed,
            unit_price=unit_price,
            tax_code_id=tax_code_id,
        )
        session.add(bill_line)

        approvable_lines.append(
            {
                "po_line_id": str(po_line_id) if po_line_id else None,
                "grn_line_id": str(grn_line_id) if grn_line_id else None,
                "qty_billed": str(qty_billed),
                "unit_price": str(unit_price),
                "tax_code_id": str(tax_code_id) if tax_code_id else None,
            }
        )

    bill.subtotal = subtotal
    bill.total_amount = subtotal + tax_total

    # Compute deterministic SHA-256 approvable content hash (FR-1212)
    approvable_content = {
        "bill_number": bill.bill_number,
        "supplier_id": str(bill.supplier_id),
        "currency": bill.currency,
        "fx_rate": str(bill.fx_rate),
        "subtotal": str(bill.subtotal),
        "tax_total": str(bill.tax_total),
        "total_amount": str(bill.total_amount),
        "lines": approvable_lines,
    }
    bill.content_hash = bill.compute_approvable_content_hash(approvable_content)

    session.add(bill)
    await session.flush()
    await session.refresh(bill)

    stmt = (
        select(VendorBill)
        .where(VendorBill.id == bill.id)
        .options(selectinload(VendorBill.lines))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def execute_three_way_match(
    session: AsyncSession,
    bill_id: UUID | str,
) -> VendorBill:
    """
    Execute strict Three-Way Match (FR-521, FR-527) against PO and GRN lines.
    Enforces 0% tolerance:
      1. qty_billed <= GoodsReceiptLine.qty_received
      2. unit_price == PurchaseOrderLine.unit_price
    Records ThreeWayMatchResult audit trail and updates bill.match_state.
    Raises ThreeWayMatchError on variance.
    """
    if isinstance(bill_id, str):
        bill_id = UUID(bill_id)

    stmt = (
        select(VendorBill)
        .where(VendorBill.id == bill_id)
        .options(selectinload(VendorBill.lines))
    )
    res = await session.execute(stmt)
    bill = res.scalar_one_or_none()
    if not bill:
        raise VendorBillNotFoundError(bill_id)

    for line in bill.lines:
        qty_variance = Decimal("0.0000")
        price_variance = Decimal("0.0000")

        if line.grn_line_id:
            grn_stmt = select(GoodsReceiptLine).where(
                GoodsReceiptLine.id == line.grn_line_id
            )
            grn_res = await session.execute(grn_stmt)
            grn_line = grn_res.scalar_one_or_none()
            if grn_line:
                # Positive variance indicates billing for more than received
                qty_variance = line.qty_billed - grn_line.qty_received

        if line.po_line_id:
            po_stmt = select(PurchaseOrderLine).where(
                PurchaseOrderLine.id == line.po_line_id
            )
            po_res = await session.execute(po_stmt)
            po_line = po_res.scalar_one_or_none()
            if po_line:
                price_variance = line.unit_price - po_line.unit_price

        # Enforce strict 0% tolerance
        is_within_tolerance = (qty_variance <= Decimal("0")) and (
            price_variance == Decimal("0")
        )

        match_result = ThreeWayMatchResult(
            bill_id=bill.id,
            bill_line_id=line.id,
            qty_variance=qty_variance,
            price_variance=price_variance,
            is_within_tolerance=is_within_tolerance,
        )
        session.add(match_result)

        if not is_within_tolerance:
            bill.match_state = VendorBillMatchState.VARIANCE_BLOCKED
            session.add(bill)
            await session.flush()
            raise ThreeWayMatchError(
                bill_id=bill.id,
                bill_line_id=line.id,
                qty_variance=str(qty_variance),
                price_variance=str(price_variance),
            )

    # All lines passed 0% tolerance
    bill.match_state = VendorBillMatchState.MATCHED

    # Update qty_billed on linked PO lines
    for line in bill.lines:
        if line.po_line_id:
            po_stmt = select(PurchaseOrderLine).where(
                PurchaseOrderLine.id == line.po_line_id
            )
            po_res = await session.execute(po_stmt)
            po_line = po_res.scalar_one_or_none()
            if po_line:
                po_line.qty_billed += line.qty_billed
                session.add(po_line)

                # Update PO status if all lines are fully billed
                po_order_stmt = (
                    select(PurchaseOrder)
                    .where(PurchaseOrder.id == po_line.po_id)
                    .options(selectinload(PurchaseOrder.lines))
                )
                po_order_res = await session.execute(po_order_stmt)
                po_order = po_order_res.scalar_one_or_none()
                if po_order and all(
                    pl.qty_billed >= pl.qty_ordered for pl in po_order.lines
                ):
                    po_order.status = PurchaseOrderStatus.BILLED
                    session.add(po_order)

    session.add(bill)
    await session.flush()
    await session.refresh(bill)

    stmt = (
        select(VendorBill)
        .where(VendorBill.id == bill.id)
        .options(selectinload(VendorBill.lines))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def post_vendor_bill(
    session: AsyncSession,
    bill_id: UUID | str,
) -> VendorBill:
    """
    Post a VendorBill to AP after verifying match_state == MATCHED.
    Transitions status to POSTED and emits purchase.bill_posted outbox domain event.
    """
    if isinstance(bill_id, str):
        bill_id = UUID(bill_id)

    stmt = (
        select(VendorBill)
        .where(VendorBill.id == bill_id)
        .options(selectinload(VendorBill.lines))
    )
    res = await session.execute(stmt)
    bill = res.scalar_one_or_none()
    if not bill:
        raise VendorBillNotFoundError(bill_id)

    if bill.match_state != VendorBillMatchState.MATCHED:
        raise ValueError(
            f"Cannot post VendorBill {bill.id}: match_state is '{bill.match_state}', expected 'MATCHED'."
        )

    bill.status = VendorBillStatus.POSTED
    bill.state = DocumentState.POSTED
    session.add(bill)
    await session.flush()

    try:
        from app.core.db.context import current_tenant

        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        tenant_id = "system"

    lines_payload = []
    for line in bill.lines:
        lines_payload.append(
            {
                "bill_line_id": str(line.id),
                "po_line_id": str(line.po_line_id) if line.po_line_id else None,
                "grn_line_id": str(line.grn_line_id) if line.grn_line_id else None,
                "qty_billed": str(line.qty_billed),
                "unit_price": str(line.unit_price),
                "tax_code_id": str(line.tax_code_id) if line.tax_code_id else None,
                "line_amount": str(line.qty_billed * line.unit_price),
            }
        )

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="purchase.bill_posted",
        tenant_id=str(tenant_id),
        payload={
            "bill_id": str(bill.id),
            "bill_number": bill.bill_number,
            "supplier_id": str(bill.supplier_id),
            "bill_date": bill.bill_date.isoformat(),
            "due_date": bill.due_date.isoformat(),
            "currency": bill.currency,
            "fx_rate": str(bill.fx_rate),
            "subtotal": str(bill.subtotal),
            "tax_total": str(bill.tax_total),
            "total_amount": str(bill.total_amount),
            "branch_id": str(bill.branch_id) if bill.branch_id else None,
            "lines": lines_payload,
        },
    )
    await event_bus.publish(event, session=session)

    await session.refresh(bill)
    return bill
