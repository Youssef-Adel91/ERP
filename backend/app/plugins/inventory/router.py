"""
app/plugins/inventory/router.py — Inventory Plugin API Routes

Real Business Logic — No Simulations.

Invoice Creation Flow (POST /invoices):
  ┌─────────────────────────────────────────────────────────────────┐
  │ 1. Validate contact_id exists in this tenant's contacts table   │
  │ 2. Validate all item_ids exist and are active                   │
  │ 3. Compute line totals (quantity × unit_price)                  │
  │ 4. Compute invoice total                                        │
  │ 5. INSERT invoice + invoice_lines rows                          │
  │ 6. COMMIT — invoice.id is now a real UUID in PostgreSQL         │
  │ 7. Deduct stock quantity from each Item (optional in MVP)       │
  │ 8. PUBLISH DomainEvent("invoice.created") to EventBus          │
  │                                                                  │
  │    ↓ Event propagates asynchronously ↓                         │
  │                                                                  │
  │ 9. accounting/events.py receives the event                      │
  │ 10. Opens tenant-scoped DB session                              │
  │ 11. INSERT JournalEntry (POSTED) + 2 TransactionLines           │
  │     DR: Accounts Receivable (1200) ← invoice total              │
  │     CR: Sales Revenue       (4010) ← invoice total              │
  │ 12. COMMIT → accounting entry persisted in PostgreSQL           │
  └─────────────────────────────────────────────────────────────────┘

  The router (steps 1–8) and event handler (steps 9–12) share ZERO direct
  imports. They communicate exclusively through the EventBus contract.
"""

import logging
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.core.event_bus import DomainEvent, get_event_bus
from app.modules.contacts.models import Contact
from app.modules.system.dependencies import CurrentUser
from app.plugins.inventory.models import Invoice, InvoiceLine, InvoiceStatus, Item
from app.plugins.inventory.schemas import (
    InvoiceCreateRequest,
    InvoiceResponse,
    ItemCreateRequest,
    ItemResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════════════════════════════
# ITEMS
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/items",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new item (product/SKU)",
    tags=["Inventory - Items"],
)
async def create_item(
    data: ItemCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ItemResponse:
    """
    Insert a new Item into the tenant's `items` table.
    SKU must be unique within the tenant schema.
    """
    # Check SKU uniqueness
    existing = await db.execute(select(Item).where(Item.sku == data.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An item with SKU '{data.sku}' already exists.",
        )

    item = Item(
        name=data.name,
        name_ar=data.name_ar,
        sku=data.sku,
        description=data.description,
        category=data.category,
        price=data.price,
        cost=data.cost,
        quantity_on_hand=data.initial_quantity,
        reorder_level=data.reorder_level,
        created_by=current_user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    logger.info("Created item '%s' (sku=%s, id=%s)", item.name, item.sku, item.id)
    return ItemResponse.model_validate(item)


@router.get(
    "/items",
    response_model=list[ItemResponse],
    summary="List all active items",
    tags=["Inventory - Items"],
)
async def list_items(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ItemResponse]:
    filters = [Item.is_active.is_(True)]
    if category:
        filters.append(Item.category == category)

    result = await db.execute(
        select(Item).where(*filters).order_by(Item.name).limit(limit).offset(offset)
    )
    return [ItemResponse.model_validate(i) for i in result.scalars().all()]


@router.get(
    "/items/{item_id}",
    response_model=ItemResponse,
    summary="Get item by ID",
    tags=["Inventory - Items"],
)
async def get_item(
    item_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> ItemResponse:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found.")
    return ItemResponse.model_validate(item)


# ══════════════════════════════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════════════════════════════


@router.post(
    "/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a real invoice — triggers journal entry via EventBus",
    description=(
        "**Full Business Flow:**\n\n"
        "1. Validates `contact_id` exists in this tenant's `contacts` table\n"
        "2. Validates all `item_id`s exist and are active\n"
        "3. Computes line totals and invoice total\n"
        "4. **INSERTs** `Invoice` + `InvoiceLine` rows into PostgreSQL\n"
        "5. **COMMITs** (invoice.id is now a real UUID)\n"
        "6. **PUBLISHes** `invoice.created` event to EventBus\n\n"
        "The accounting event handler then (asynchronously):\n"
        "- Opens a tenant-scoped DB session\n"
        "- INSERTs a balanced `JournalEntry` + 2 `TransactionLine` rows\n"
        "- COMMITs the accounting entry\n\n"
        "Verify at `GET /api/v1/accounting/journal-entries`"
    ),
    tags=["Inventory - Invoices"],
)
async def create_invoice(
    data: InvoiceCreateRequest,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> InvoiceResponse:
    """
    Create a sales invoice with full DB persistence and EventBus notification.

    The key sequencing:
      db.commit() MUST happen BEFORE event_bus.publish()
      Reason: the event handler might immediately query the DB for the invoice.
              If the commit hasn't happened, the handler would see no data.
    """
    tenant_id: str = request.state.tenant_id or str(current_user.tenant_id)

    # ── Step 1: Validate Contact exists ───────────────────────────────────────
    contact_result = await db.execute(
        select(Contact).where(Contact.id == data.contact_id)
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact '{data.contact_id}' not found in this tenant.",
        )

    # ── Step 2: Validate and resolve all Items ────────────────────────────────
    item_ids = [line.item_id for line in data.lines]
    items_result = await db.execute(
        select(Item).where(Item.id.in_(item_ids), Item.is_active.is_(True))
    )
    items_map: dict[UUID, Item] = {
        item.id: item for item in items_result.scalars().all()
    }

    missing = [str(iid) for iid in item_ids if iid not in items_map]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Items not found or inactive: {missing}",
        )

    # ── Step 3: Compute line totals ───────────────────────────────────────────
    invoice_number = f"INV-{uuid4().hex[:8].upper()}"
    invoice_total = Decimal("0.0000")
    lines_to_insert: list[tuple] = []  # (line_data, computed_total)

    for line_req in data.lines:
        item = items_map[line_req.item_id]
        unit_price = line_req.unit_price if line_req.unit_price is not None else item.price
        total_price = (line_req.quantity * unit_price).quantize(Decimal("0.0001"))
        invoice_total += total_price
        lines_to_insert.append((line_req, item, unit_price, total_price))

    # ── Step 4: INSERT Invoice ────────────────────────────────────────────────
    invoice = Invoice(
        invoice_number=invoice_number,
        contact_id=data.contact_id,
        total_amount=invoice_total,
        status=InvoiceStatus.DRAFT,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(invoice)
    await db.flush()  # Get invoice.id without committing yet

    # ── Step 5: INSERT InvoiceLines ───────────────────────────────────────────
    for line_req, item, unit_price, total_price in lines_to_insert:
        invoice_line = InvoiceLine(
            invoice_id=invoice.id,
            item_id=item.id,
            quantity=line_req.quantity,
            unit_price=unit_price,
            total_price=total_price,
        )
        db.add(invoice_line)

    # ── Step 6: COMMIT — invoice.id is now persisted ──────────────────────────
    await db.commit()
    await db.refresh(invoice)  # Refresh to load lines relationship (selectin)

    logger.info(
        "✅ Invoice '%s' created (id=%s, amount=%s, contact=%s, tenant=%s)",
        invoice_number,
        invoice.id,
        invoice_total,
        contact.name,
        tenant_id,
    )

    # ── Step 7: PUBLISH DomainEvent ───────────────────────────────────────────
    # MUST come AFTER commit. The event handler opens its own session and
    # may read from the DB. If we publish before commit, the handler sees nothing.
    event = DomainEvent(
        event_type="invoice.created",
        tenant_id=tenant_id,
        payload={
            "invoice_id": str(invoice.id),
            "invoice_number": invoice_number,
            "amount": str(invoice_total),
            "contact_id": str(invoice.contact_id),
            "customer_name": contact.name,
            # Accounting integration: account codes for journal entry
            "ar_account_code": data.ar_account_code,
            "revenue_account_code": data.revenue_account_code,
            "created_by_user_id": str(current_user.id),
        },
    )

    event_bus = get_event_bus()
    await event_bus.publish(event)

    logger.info(
        "📤 Published invoice.created event (event_id=%s) for invoice %s",
        event.event_id,
        invoice_number,
    )

    return InvoiceResponse.model_validate(invoice)


@router.get(
    "/invoices",
    response_model=list[InvoiceResponse],
    summary="List invoices with optional filtering",
    tags=["Inventory - Invoices"],
)
async def list_invoices(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
    contact_id: UUID | None = Query(default=None),
    invoice_status: InvoiceStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[InvoiceResponse]:
    filters = []
    if contact_id:
        filters.append(Invoice.contact_id == contact_id)
    if invoice_status:
        filters.append(Invoice.status == invoice_status)

    result = await db.execute(
        select(Invoice)
        .where(*filters)
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [InvoiceResponse.model_validate(inv) for inv in result.scalars().all()]


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Get invoice by ID (includes line items)",
    tags=["Inventory - Invoices"],
)
async def get_invoice(
    invoice_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> InvoiceResponse:
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found.")
    return InvoiceResponse.model_validate(invoice)
