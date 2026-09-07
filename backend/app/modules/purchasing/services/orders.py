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
from app.modules.approvals.services.approval_engine import find_matching_rules, submit_for_approval
from app.modules.contacts.models import Contact, ContactType
from app.modules.purchasing.exceptions import (
    InvalidPOStateError,
    PurchaseOrderNotFoundError,
    SupplierNotFoundError,
)
from app.modules.purchasing.models.core import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
)


def _po_approvable_content(po: PurchaseOrder) -> dict:
    """Same approvable-content shape used at PO creation (see create_purchase_order),
    rebuilt from a loaded PurchaseOrder + its lines so the content hash stays
    stable across create -> submit-for-approval as long as nothing changed."""
    return {
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

    # Validated lookup: `supplier_id` has no DB-level foreign key to
    # tenant.contacts.id (see PurchaseOrder.supplier_id), so confirm it
    # actually resolves to a SUPPLIER-type contact before the PO is
    # created — otherwise a PO can silently point at a nonexistent or
    # customer-only contact with no error until someone tries to bill it.
    supplier_stmt = select(Contact).where(
        Contact.id == supplier_id,
        Contact.contact_type == ContactType.SUPPLIER,
    )
    supplier = (await session.execute(supplier_stmt)).scalar_one_or_none()
    if supplier is None:
        raise SupplierNotFoundError(supplier_id)

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
    requested_by: UUID,
) -> PurchaseOrder:
    """
    Transitions a PurchaseOrder from DRAFT or APPROVED state to CONFIRMED.

    Approval gate (Wave 2): if an active `ApprovalRule` for document_type
    "purchase_order" matches this PO's fields (e.g. total_amount over a
    threshold), confirming a DRAFT PO instead routes it through the
    Approval Engine — the PO is submitted for approval (state ->
    PENDING_APPROVAL) and this call returns without confirming; a second
    call to `confirm_purchase_order` after the request is approved (state ->
    APPROVED, via POST /approvals/requests/{id}/decide) actually confirms it.

    Tenants with **no matching active rules** (the default — no tenant has
    any ApprovalRule configured yet) see zero behavior change: DRAFT goes
    straight to APPROVED then CONFIRMED in this same call, exactly as
    before this gate was added.
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

    if po.state == DocumentState.DRAFT:
        matching_rules = await find_matching_rules(
            session,
            document_type="purchase_order",
            fields={"total_amount": po.total_amount},
        )
        if matching_rules:
            rule = matching_rules[0]
            await submit_for_approval(
                session=session,
                document_type="purchase_order",
                document_id=po.id,
                document=po,
                requested_by=requested_by,
                approvable_content=_po_approvable_content(po),
                rule_id=rule.id,
                rule_version=rule.version,
            )
            await session.flush()
            await session.refresh(po)
            return po
        po.state = DocumentState.APPROVED
    elif po.state in (DocumentState.PENDING_APPROVAL, DocumentState.REJECTED):
        raise InvalidPOStateError(po.id, po.state.value, "confirm")

    po.status = PurchaseOrderStatus.CONFIRMED
    session.add(po)
    await session.flush()
    await session.refresh(po)
    return po
