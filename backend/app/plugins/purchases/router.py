
import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.modules.contacts.models import Contact, ContactType
from app.modules.system.dependencies import CurrentUser
from app.plugins.inventory.models import Item
from app.plugins.purchases.models import PurchaseInvoice, PurchaseInvoiceLine, PurchaseInvoiceStatus
from app.plugins.purchases.schemas import PurchaseInvoiceCreateRequest, PurchaseInvoiceResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/invoices",
    response_model=PurchaseInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase invoice",
)
async def create_purchase_invoice(
    data: PurchaseInvoiceCreateRequest,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> PurchaseInvoiceResponse:
    # 1. Validate Supplier
    contact_result = await db.execute(
        select(Contact).where(Contact.id == data.supplier_id, Contact.contact_type == ContactType.SUPPLIER),
    )
    supplier = contact_result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier '{data.supplier_id}' not found in this tenant.",
        )

    # 2. Validate Items
    item_ids = [line.item_id for line in data.lines]
    items_result = await db.execute(select(Item).where(Item.id.in_(item_ids)))
    items_map: dict[UUID, Item] = {item.id: item for item in items_result.scalars().all()}

    missing = [str(iid) for iid in item_ids if iid not in items_map]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Items not found: {missing}",
        )

    # 3. Compute Invoice Total
    invoice_total = Decimal("0.0000")
    lines_to_insert: list[tuple] = []

    for line_req in data.lines:
        item = items_map[line_req.item_id]
        line_total = (line_req.quantity * line_req.unit_price).quantize(Decimal("0.0001"))
        invoice_total += line_total
        lines_to_insert.append((line_req, item, line_total))

    # 4. Create PurchaseInvoice
    invoice = PurchaseInvoice(
        supplier_id=data.supplier_id,
        invoice_date=data.invoice_date,
        total_amount=invoice_total,
        status=PurchaseInvoiceStatus.CONFIRMED,
        created_by=current_user.id,
    )
    db.add(invoice)
    await db.flush()  # to get invoice.id

    # 5. Create PurchaseInvoiceLines and Update Inventory
    for line_req, item, line_total in lines_to_insert:
        inv_line = PurchaseInvoiceLine(
            invoice_id=invoice.id,
            item_id=item.id,
            quantity=line_req.quantity,
            unit_price=line_req.unit_price,
            line_total=line_total,
        )
        db.add(inv_line)

        # Update Inventory stock
        item.quantity_on_hand += line_req.quantity

    # 6. Commit Transaction
    await db.commit()
    await db.refresh(invoice)

    # EVENT BUS INTEGRATION
    from app.core.event_bus import DomainEvent, get_event_bus
    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="purchase_invoice.confirmed",
        tenant_id=request.state.tenant_id or str(current_user.tenant_id),
        payload={"invoice_id": str(invoice.id), "total": str(invoice_total)},
    )
    await event_bus.publish(event)
    # This triggers Accounting Core to create Journal Entry (Inventory vs. AP)

    return PurchaseInvoiceResponse.model_validate(invoice)


@router.get(
    "/invoices",
    response_model=list[PurchaseInvoiceResponse],
    summary="List purchase invoices",
)
async def list_purchase_invoices(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PurchaseInvoiceResponse]:
    result = await db.execute(
        select(PurchaseInvoice)
        .order_by(PurchaseInvoice.created_at.desc())
        .limit(limit)
        .offset(offset),
    )
    return [PurchaseInvoiceResponse.model_validate(inv) for inv in result.scalars().all()]
