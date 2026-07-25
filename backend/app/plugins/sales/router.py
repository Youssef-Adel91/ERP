
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
from app.plugins.sales.models import SalesInvoice, SalesInvoiceLine, SalesInvoiceStatus
from app.plugins.sales.schemas import SalesInvoiceCreateRequest, SalesInvoiceResponse

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/invoices",
    response_model=SalesInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sales invoice",
    tags=["Sales Plugin"],
)
async def create_sales_invoice(
    data: SalesInvoiceCreateRequest,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> SalesInvoiceResponse:
    tenant_id: str = request.state.tenant_id or str(current_user.tenant_id)

    # 1. Verify customer exists and is a CUSTOMER
    contact_result = await db.execute(select(Contact).where(Contact.id == data.customer_id, Contact.contact_type == ContactType.CUSTOMER))
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{data.customer_id}' not found.",
        )

    # 2. Fetch all requested items
    item_ids = [line.item_id for line in data.lines]
    items_result = await db.execute(select(Item).where(Item.id.in_(item_ids), Item.is_active.is_(True)))
    items_map: dict[UUID, Item] = {item.id: item for item in items_result.scalars().all()}

    missing = [str(iid) for iid in item_ids if iid not in items_map]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Items not found or inactive: {missing}",
        )

    invoice_total = Decimal("0.0000")
    lines_to_insert: list[tuple] = [] 

    # 3. Verify stock levels & calculate totals
    for line_req in data.lines:
        item = items_map[line_req.item_id]
        
        if item.quantity_on_hand < line_req.quantity:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for item {item.name}. Requested: {line_req.quantity}, Available: {item.quantity_on_hand}",
            )

        unit_price = line_req.unit_price if line_req.unit_price is not None else item.price
        total_price = (line_req.quantity * unit_price).quantize(Decimal("0.0001"))
        invoice_total += total_price
        lines_to_insert.append((line_req, item, unit_price, total_price))

    # 4. Insert Invoice header
    invoice = SalesInvoice(
        customer_id=data.customer_id,
        total_amount=invoice_total,
        status=SalesInvoiceStatus.CONFIRMED, # Confirmed directly in MVP
        created_by=current_user.id,
    )
    db.add(invoice)
    await db.flush()

    # 5. Insert lines & deduct stock
    for line_req, item, unit_price, total_price in lines_to_insert:
        invoice_line = SalesInvoiceLine(
            invoice_id=invoice.id,
            item_id=item.id,
            quantity=line_req.quantity,
            unit_price=unit_price,
            line_total=total_price,
        )
        db.add(invoice_line)
        item.quantity_on_hand -= line_req.quantity # Deduct stock

    await db.commit()
    await db.refresh(invoice)

    # 6. EVENT BUS INTEGRATION
    from app.core.event_bus import get_event_bus, DomainEvent
    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="sales_invoice.confirmed",
        tenant_id=tenant_id,
        payload={"invoice_id": str(invoice.id), "total": str(invoice_total)}
    )
    await event_bus.publish(event)
    # This triggers Accounting Core to create Journal Entry (AR vs. Revenue)

    return SalesInvoiceResponse.model_validate(invoice)


@router.get(
    "/invoices",
    response_model=list[SalesInvoiceResponse],
    summary="List sales invoices",
    tags=["Sales Plugin"],
)
async def list_sales_invoices(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    customer_id: UUID | None = Query(default=None),
    invoice_status: SalesInvoiceStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SalesInvoiceResponse]:
    filters = []
    if customer_id:
        filters.append(SalesInvoice.customer_id == customer_id)
    if invoice_status:
        filters.append(SalesInvoice.status == invoice_status)

    result = await db.execute(
        select(SalesInvoice)
        .where(*filters)
        .order_by(SalesInvoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [SalesInvoiceResponse.model_validate(inv) for inv in result.scalars().all()]
