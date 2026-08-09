"""
app/modules/pos/api.py — Point of Sale API (built from scratch, Phase 6 gap)

Minimal, solid surface per explicit instruction:
  - Shifts: open/close a cashier's cash session.
  - Checkout: rings up a cart. Does NOT reimplement invoicing/inventory/
    accounting — it calls the real app.modules.sales.services.invoicing
    pipeline (create_adhoc_invoice + post_invoice), exactly like any other
    ad-hoc billing flow (Hospitality folio, Rental close-out). This means a
    POS sale correctly hits the ledger (via the sales.invoice_posted event
    -> accounting consumer) and inventory/costing the same way.
  - Catalog: a POS-shaped read view over Item + ItemVariant (the grid needs
    price, and price lives on ItemVariant — there is no existing endpoint
    that joins the two, so this module adds one rather than reusing the
    bare /inventory/items list, which has no price).

Walk-in customers: create_adhoc_invoice() requires a contact_id. POS
checkout accepts an optional contact_id; if omitted, it resolves (and
lazily creates, once) a per-tenant "Walk-in Customer" / "عميل نقدي" Contact
and uses that — a pragmatic, explicit choice rather than fabricating a
required customer-selection step for cash counter sales.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.contacts.models import Contact, ContactStatus, ContactType
from app.modules.inventory.models.core import Item, ItemVariant
from app.modules.pos.models import CashShift, PosSale, ShiftStatus
from app.modules.sales.services.invoicing import create_adhoc_invoice, post_invoice
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/pos", tags=["Point of Sale"])

WALK_IN_CONTACT_NAME = "عميل نقدي (Walk-in Customer)"


async def _get_or_create_walkin_contact(session: AsyncSession) -> Contact:
    stmt = select(Contact).where(Contact.name == WALK_IN_CONTACT_NAME)
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact:
        return contact
    contact = Contact(
        name=WALK_IN_CONTACT_NAME,
        contact_type=ContactType.CUSTOMER,
        status=ContactStatus.ACTIVE,
    )
    session.add(contact)
    await session.flush()
    return contact


# ── Catalog (POS-shaped: Item + ItemVariant joined, price included) ───────────


class PosCatalogEntry(BaseModel):
    item_id: UUID
    variant_id: UUID
    sku: str
    name: str
    price: Decimal


@router.get("/catalog", response_model=list[PosCatalogEntry])
async def get_catalog(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    One row per sellable variant, ready for the POS grid. Items with no
    variant have no price and are intentionally omitted — nothing to sell
    them at.
    """
    stmt = select(Item, ItemVariant).join(ItemVariant, ItemVariant.item_id == Item.id)
    rows = (await session.execute(stmt)).all()
    return [
        PosCatalogEntry(
            item_id=item.id,
            variant_id=variant.id,
            sku=variant.sku,
            name=variant.name or item.name,
            price=variant.price,
        )
        for item, variant in rows
    ]


# ── Cash shifts ─────────────────────────────────────────────────────────────


class ShiftOpenIn(BaseModel):
    opening_balance: Decimal = Decimal("0.00")


class ShiftCloseIn(BaseModel):
    closing_balance: Decimal


@router.get("/shifts/current", response_model=CashShift | None)
async def get_current_shift(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    stmt = (
        select(CashShift)
        .where(CashShift.opened_by == current_user.id, CashShift.status == ShiftStatus.OPEN)
        .order_by(CashShift.opened_at.desc())
    )
    return (await session.execute(stmt)).scalars().first()


@router.post("/shifts/open", response_model=CashShift, status_code=status.HTTP_201_CREATED)
async def open_shift(
    data: ShiftOpenIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    existing_stmt = select(CashShift).where(
        CashShift.opened_by == current_user.id, CashShift.status == ShiftStatus.OPEN
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="لديك وردية مفتوحة بالفعل. أغلقها أولًا قبل فتح وردية جديدة.",
        )

    shift = CashShift(
        opened_by=current_user.id,
        status=ShiftStatus.OPEN,
        opening_balance=data.opening_balance,
    )
    session.add(shift)
    await session.commit()
    await session.refresh(shift)
    return shift


@router.post("/shifts/{shift_id}/close", response_model=CashShift)
async def close_shift(
    shift_id: UUID,
    data: ShiftCloseIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    shift = await session.get(CashShift, shift_id)
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found.")
    if shift.opened_by != current_user.id:
        # Previously any authenticated user of the tenant could close (and
        # thus reconcile/lock the variance on) any other cashier's shift —
        # a real cash-handling integrity gap, not just a permissions nit.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لا يمكنك إغلاق وردية كاشير آخر.",
        )
    if shift.status != ShiftStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift is already closed.")

    sales_stmt = select(PosSale).where(PosSale.shift_id == shift.id)
    sales = (await session.execute(sales_stmt)).scalars().all()
    total_sales = sum((s.amount for s in sales), Decimal("0.00"))

    shift.expected_balance = shift.opening_balance + total_sales
    shift.closing_balance = data.closing_balance
    shift.variance = data.closing_balance - shift.expected_balance
    shift.status = ShiftStatus.CLOSED
    shift.closed_by = current_user.id
    shift.closed_at = datetime.now(UTC)

    session.add(shift)
    await session.commit()
    await session.refresh(shift)
    return shift


# ── Checkout ────────────────────────────────────────────────────────────────


class CheckoutLineIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    qty: Decimal
    unit_price: Decimal


class CheckoutIn(BaseModel):
    shift_id: UUID
    contact_id: UUID | None = None
    lines: list[CheckoutLineIn]
    payment_method: str = "cash"


class CheckoutOut(BaseModel):
    invoice_id: UUID
    invoice_number: str
    grand_total: Decimal
    pos_sale_id: UUID


@router.post("/checkout", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
async def checkout(
    data: CheckoutIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Rings up a cart: creates a DRAFT ad-hoc SalesInvoice, posts it
    immediately (hits the ledger + inventory via the real sales pipeline),
    and records a PosSale row against the given shift for cash
    reconciliation at close-out.
    """
    shift = await session.get(CashShift, data.shift_id)
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found.")
    if shift.opened_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لا يمكنك البيع على وردية كاشير آخر.",
        )
    if shift.status != ShiftStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="لا يمكن البيع على وردية مغلقة.")

    if not data.lines:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="السلة فارغة.")

    contact_id = data.contact_id
    if contact_id is None:
        walkin = await _get_or_create_walkin_contact(session)
        contact_id = walkin.id

    line_dicts = [
        {
            "item_id": line.item_id,
            "variant_id": line.variant_id,
            "qty": line.qty,
            "unit_price": line.unit_price,
        }
        for line in data.lines
    ]

    try:
        invoice = await create_adhoc_invoice(session, contact_id=contact_id, lines=line_dicts)
        await session.flush()
        invoice = await post_invoice(session=session, invoice_id=invoice.id)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    pos_sale = PosSale(
        shift_id=shift.id,
        invoice_id=invoice.id,
        cashier_id=current_user.id,
        amount=invoice.grand_total,
        payment_method=data.payment_method,
    )
    session.add(pos_sale)
    await session.commit()
    await session.refresh(pos_sale)

    return CheckoutOut(
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        grand_total=invoice.grand_total,
        pos_sale_id=pos_sale.id,
    )
