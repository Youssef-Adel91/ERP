"""
app/plugins/inventory/service.py — Inventory Plugin Service

This plugin manages products, stock, and sales invoices.

DECOUPLING CONTRACT:
  ✅ This plugin imports from app.core.event_bus (shared contract only)
  ✅ This plugin emits events to communicate with the accounting core
  ❌ This plugin NEVER imports from app.modules.accounting
  ❌ This plugin NEVER imports from app.modules.contacts
  ❌ This plugin NEVER calls accounting service functions directly

When a SaleInvoice is created, this service emits `invoice.created`.
The accounting module's event handler (events.py) listens and creates
the corresponding double-entry journal entry automatically.

This is the CORRECT implementation of the Event-Driven, Decoupled Monolith pattern.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import InvoiceCreatedEvent, PaymentReceivedEvent, get_event_bus
from app.plugins.inventory.models import (
    Product,
    SaleInvoice,
    SaleInvoiceItem,
    SaleInvoiceStatus,
)
from app.plugins.inventory.schemas import (
    ProductCreateRequest,
    SaleInvoiceCreateRequest,
)

logger = logging.getLogger(__name__)


class ProductNotFoundError(LookupError):
    """Raised when a product doesn't exist."""


class InsufficientStockError(ValueError):
    """Raised when a sale would exceed available stock."""


class InvoiceNotFoundError(LookupError):
    """Raised when an invoice doesn't exist."""


# ── Product Service ───────────────────────────────────────────────────────────


async def create_product(
    data: ProductCreateRequest,
    created_by: UUID,
    db: AsyncSession,
) -> Product:
    """Create a new product and add it to inventory."""
    product = Product(
        sku=data.sku,
        name=data.name,
        name_ar=data.name_ar,
        description=data.description,
        unit_cost=data.unit_cost,
        unit_price=data.unit_price,
        quantity_on_hand=data.initial_quantity,
        reorder_level=data.reorder_level,
        category=data.category,
        created_by=created_by,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    logger.info("Created product '%s' (SKU: %s)", product.name, product.sku)
    return product


async def get_products(db: AsyncSession, limit: int = 50, offset: int = 0) -> list[Product]:
    """List all active products."""
    result = await db.execute(
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.name)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


# ── Sale Invoice Service ──────────────────────────────────────────────────────


async def create_sale_invoice(
    data: SaleInvoiceCreateRequest,
    created_by: UUID,
    db: AsyncSession,
) -> SaleInvoice:
    """
    Create a new sale invoice and emit the `invoice.created` event.

    Workflow:
      1. Validate stock availability for each line item.
      2. Create the SaleInvoice and SaleInvoiceItem records.
      3. Deduct stock from Product.quantity_on_hand.
      4. Commit the transaction.
      5. Emit `invoice.created` event → accounting core handles journal entry.

    The accounting journal entry is NOT created here.
    It is created by the accounting module's event handler.
    """
    invoice_number = f"INV-{uuid4().hex[:8].upper()}"
    total_amount = Decimal("0")

    # 1. Validate stock and compute total
    line_items = []
    for item_data in data.items:
        product_result = await db.execute(
            select(Product).where(Product.id == item_data.product_id).with_for_update()
        )
        product = product_result.scalar_one_or_none()

        if not product:
            raise ProductNotFoundError(f"Product '{item_data.product_id}' not found.")

        if product.quantity_on_hand < item_data.quantity:
            raise InsufficientStockError(
                f"Insufficient stock for '{product.name}': "
                f"available={product.quantity_on_hand}, requested={item_data.quantity}"
            )

        unit_price = item_data.unit_price or product.unit_price
        line_total = unit_price * item_data.quantity
        total_amount += line_total
        line_items.append((product, item_data, unit_price, line_total))

    # 2. Create invoice header
    invoice = SaleInvoice(
        invoice_number=invoice_number,
        customer_contact_id=data.customer_contact_id,
        status=SaleInvoiceStatus.DRAFT,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(invoice)
    await db.flush()

    # 3. Create line items and deduct stock
    for product, item_data, unit_price, line_total in line_items:
        item = SaleInvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            quantity=item_data.quantity,
            unit_price=unit_price,
            total_price=line_total,
        )
        db.add(item)
        product.quantity_on_hand -= item_data.quantity

    invoice.total_amount = total_amount
    invoice.status = SaleInvoiceStatus.CONFIRMED

    await db.commit()
    await db.refresh(invoice)

    logger.info(
        "Sale invoice '%s' created: total=%s (created_by=%s)",
        invoice_number,
        total_amount,
        created_by,
    )

    # 4. Emit `invoice.created` — accounting core will pick this up
    #    The payload contains everything the accounting handler needs
    #    to create a journal entry WITHOUT importing anything from this plugin.
    event_bus = get_event_bus()
    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=str(data.tenant_id),
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice_number,
                "amount": str(total_amount),
                # These account IDs should come from the tenant's Chart of Accounts
                # In production, they are retrieved from tenant settings/config.
                # Here we pass them from the request for the MVP.
                "ar_account_id": str(data.ar_account_id),
                "revenue_account_id": str(data.revenue_account_id),
                "created_by_user_id": str(created_by),
            },
        )
    )

    return invoice


async def get_invoices(
    db: AsyncSession,
    customer_contact_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SaleInvoice]:
    """List sale invoices, optionally filtered by customer."""
    query = (
        select(SaleInvoice)
        .order_by(SaleInvoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if customer_contact_id:
        query = query.where(SaleInvoice.customer_contact_id == customer_contact_id)

    result = await db.execute(query)
    return list(result.scalars().all())
