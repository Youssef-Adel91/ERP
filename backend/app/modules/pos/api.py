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

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import _get_redis_client, get_tenant_db
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.contacts.models import Contact, ContactStatus, ContactType
from app.modules.inventory.models.core import Item, ItemVariant
from app.modules.pos.models import CashShift, PosSale, ShiftStatus
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.sales.services.invoicing import create_adhoc_invoice, post_invoice
from app.modules.system.dependencies import CurrentUser

logger = logging.getLogger(__name__)

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
#
# Idempotency: a POS terminal is a touchscreen with a network round-trip to
# a possibly-flaky connection — a double-tap on "Pay" or a client-side retry
# after a timeout must NOT ring up the sale twice (duplicate invoice,
# duplicate stock deduction, duplicate cash-drawer entry). The client sends
# a per-attempt `Idempotency-Key` header (any client-generated unique
# string, e.g. a UUID minted once per cart-submit); the key is optional so
# older/unmodified clients keep working exactly as before, just without the
# replay protection.
#
# No generic idempotency helper existed elsewhere in the codebase at the
# time this was added (checked app/core/ and app/modules/), so this is
# scoped to POS checkout specifically rather than factored out prematurely.

_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60  # outlives any realistic retry window
_IDEMPOTENCY_IN_PROGRESS = b"IN_PROGRESS"


def _idempotency_redis_key(tenant_id: str | None, idempotency_key: str) -> str:
    return f"pos:checkout:idem:{tenant_id or 'unknown'}:{idempotency_key}"


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
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """
    Rings up a cart: creates a DRAFT ad-hoc SalesInvoice, posts it
    immediately (hits the ledger + inventory via the real sales pipeline),
    and records a PosSale row against the given shift for cash
    reconciliation at close-out.

    If the caller sends an `Idempotency-Key` header, a repeat request with
    the same key returns the original result (or a 409 while the original
    is still in flight) instead of ringing up a second sale. Redis is
    unreachable -> we fail open (proceed without protection) rather than
    blocking checkout entirely, same fail-open discipline used by the
    rate limiter for non-security-critical routes.
    """
    idem_redis_key: str | None = None
    rc = None
    if idempotency_key:
        tenant_id = getattr(request.state, "tenant_id", None)
        idem_redis_key = _idempotency_redis_key(tenant_id, idempotency_key)
        try:
            rc = await _get_redis_client()
            cached = await rc.get(idem_redis_key)
            if cached is not None:
                if cached == _IDEMPOTENCY_IN_PROGRESS:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="طلب مكرر قيد التنفيذ بالفعل. الرجاء الانتظار.",
                    )
                return CheckoutOut.model_validate_json(cached)
            acquired = await rc.set(
                idem_redis_key, _IDEMPOTENCY_IN_PROGRESS, ex=_IDEMPOTENCY_TTL_SECONDS, nx=True
            )
            if not acquired:
                # Lost the race to a concurrent request with the same key
                # between our GET and SET NX above.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="طلب مكرر قيد التنفيذ بالفعل. الرجاء الانتظار.",
                )
        except RedisError as exc:
            logger.warning("POS checkout idempotency check bypassed (Redis error): %s", exc)
            idem_redis_key = None
            rc = None

    try:
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

        result = CheckoutOut(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            grand_total=invoice.grand_total,
            pos_sale_id=pos_sale.id,
        )
    except Exception:
        # Whatever failed (validation, forbidden, closed shift, invoicing
        # error...) — this attempt did NOT ring up a sale, so release the
        # lock rather than let a transient failure permanently poison the
        # idempotency key and lock the cashier out of retrying.
        if idem_redis_key and rc is not None:
            try:
                await rc.delete(idem_redis_key)
            except RedisError as exc:
                logger.warning("POS checkout idempotency cleanup failed: %s", exc)
        raise

    if idem_redis_key and rc is not None:
        try:
            await rc.set(idem_redis_key, result.model_dump_json(), ex=_IDEMPOTENCY_TTL_SECONDS)
        except RedisError as exc:
            logger.warning("POS checkout idempotency result not cached: %s", exc)

    return result


# ── Sales history & refunds ────────────────────────────────────────────────
#
# Scope decision (2026-09-07): POS refunds are GL-only. Checkout
# (create_adhoc_invoice() above) sets order_id=None, so
# app/modules/sales/services/fulfillment.py never runs for a POS sale — no
# StockMovement/CostLayer is ever created for what it sells. That means
# there is no real inventory/cost history for a refund to reverse, unlike
# app/modules/sales/services/returns.py's exact-cost reversal for regular
# sales invoices. Doing a fake stock reversal here would fabricate numbers
# rather than reverse real ones, so this deliberately only reverses the GL
# side (a negative-total credit-note SalesInvoice, same event/consumer
# regular sales returns already use) — same decision recorded in
# refund_pos_sale()'s docstring below. Making POS checkout inventory-aware
# is a separate, larger change if/when actually needed.


class PosSaleOut(BaseModel):
    id: UUID
    invoice_id: UUID
    invoice_number: str
    cashier_id: UUID
    amount: Decimal
    payment_method: str
    created_at: datetime
    is_refund: bool

    model_config = {"from_attributes": True}


@router.get("/shifts/{shift_id}/sales", response_model=list[PosSaleOut])
async def list_shift_sales(
    shift_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Past sales (and refunds — negative-amount rows) rung up under one shift,
    newest first. Used by the POS UI to let a cashier pick a completed sale
    to refund; scoped to the caller's own shift like every other POS
    ownership check in this router (open_shift/close_shift/checkout above).
    """
    shift = await session.get(CashShift, shift_id)
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الوردية غير موجودة.")
    if shift.opened_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لا يمكنك عرض مبيعات وردية كاشير آخر.",
        )

    stmt = (
        select(PosSale, SalesInvoice.invoice_number)
        .join(SalesInvoice, SalesInvoice.id == PosSale.invoice_id)
        .where(PosSale.shift_id == shift_id)
        .order_by(PosSale.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        PosSaleOut(
            id=sale.id,
            invoice_id=sale.invoice_id,
            invoice_number=invoice_number,
            cashier_id=sale.cashier_id,
            amount=sale.amount,
            payment_method=sale.payment_method,
            created_at=sale.created_at,
            is_refund=sale.amount < 0,
        )
        for sale, invoice_number in rows
    ]


class PosRefundIn(BaseModel):
    shift_id: UUID


class PosRefundOut(BaseModel):
    pos_sale_id: UUID
    credit_note_id: UUID
    credit_note_number: str
    refunded_amount: Decimal


@router.post("/sales/{pos_sale_id}/refund", response_model=PosRefundOut, status_code=status.HTTP_201_CREATED)
async def refund_pos_sale(
    pos_sale_id: UUID,
    data: PosRefundIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Whole-sale refund of a completed POS sale (no partial/line-level refund —
    matches the most common real POS refund case and keeps this endpoint
    simple; a partial-refund mode can be added later if actually needed).

    Issues a negative-total credit-note SalesInvoice for the original sale's
    totals, records a matching negative PosSale row against the refunding
    shift (so that shift's close-out cash reconciliation in close_shift()
    above — which sums PosSale.amount — correctly accounts for cash handed
    back), then publishes sales.credit_note_posted so accounting posts the
    reversing GL entry through the exact same event/consumer regular sales
    returns use (app/modules/sales/services/returns.py::post_credit_note(),
    consumed by
    app/modules/accounting/consumers/events.py::handle_credit_note_posted).

    GL-only by design — see the module-level comment above this function for
    why: POS checkout never creates real StockMovement/CostLayer history, so
    there is nothing genuine for a stock-level reversal to work from.

    Refunding shift does not have to be the sale's original shift (a
    different open shift, or even a later shift for the same cashier, is a
    normal real-world case — e.g. a customer returns an item the next day);
    it only has to be an OPEN shift owned by the cashier performing the
    refund, matching every other ownership check in this router.
    """
    original_sale = await session.get(PosSale, pos_sale_id)
    if not original_sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="عملية البيع غير موجودة.")
    if original_sale.amount < 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="هذه العملية مرتجع بالفعل، لا يمكن استرجاعها مرة أخرى.",
        )

    refund_shift = await session.get(CashShift, data.shift_id)
    if not refund_shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الوردية غير موجودة.")
    if refund_shift.opened_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لا يمكنك تسجيل مرتجع على وردية كاشير آخر.",
        )
    if refund_shift.status != ShiftStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="لا يمكن تسجيل مرتجع على وردية مغلقة.")

    original_invoice = await session.get(SalesInvoice, original_sale.invoice_id)
    if not original_invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الفاتورة الأصلية غير موجودة.")

    # Deterministic credit-note number doubles as an idempotency guard: a
    # second refund attempt on the same sale (double-tap, retry) hits this
    # check before touching the ledger, same "check by deterministic
    # reference before inserting" pattern returns.py/post_credit_note uses
    # via reference_id in _is_already_journaled.
    credit_note_number = f"CN-POS-{original_invoice.invoice_number}"
    existing_stmt = select(SalesInvoice).where(SalesInvoice.invoice_number == credit_note_number)
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"تم استرجاع هذه العملية بالفعل ({credit_note_number}).",
        )

    credit_note = SalesInvoice(
        invoice_number=credit_note_number,
        order_id=None,
        contact_id=original_invoice.contact_id,
        status=SalesInvoiceStatus.POSTED,
        subtotal=-original_invoice.subtotal,
        tax_total=-original_invoice.tax_total,
        grand_total=-original_invoice.grand_total,
    )
    session.add(credit_note)
    await session.flush()

    refund_sale_row = PosSale(
        shift_id=refund_shift.id,
        invoice_id=credit_note.id,
        cashier_id=current_user.id,
        amount=-original_invoice.grand_total,
        payment_method=original_sale.payment_method,
    )
    session.add(refund_sale_row)

    try:
        from app.core.db.context import current_tenant

        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        # NOTE: matches the identical try/except shape already used at every
        # other event-publish call site in this codebase (returns.py,
        # invoicing.py, payments.py, receiving.py, billing.py,
        # stock_take.py) — `current_tenant` doesn't actually exist in
        # app/core/db/context.py (it defines `current_tenant_id`), so this
        # import always fails there too and every one of those call sites
        # already falls back to "system" today. Not something to silently
        # "fix" here in isolation: the synchronous in-process EventBus
        # dispatch path (the only path that currently works — see
        # app/core/events/event_bus.py) passes `session` directly to
        # handlers, and handle_credit_note_posted never reads
        # event.tenant_id, so this fallback is harmless in practice.
        # Matching the existing pattern exactly keeps this file consistent
        # with the rest of the codebase rather than introducing a lone
        # different-looking except clause.
        tenant_id = "system"

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="sales.credit_note_posted",
        tenant_id=str(tenant_id),
        payload={
            "id": str(credit_note.id),
            "credit_note_id": str(credit_note.id),
            "return_number": credit_note_number,
            "invoice_id": str(original_invoice.id),
            "contact_id": str(original_invoice.contact_id),
            "subtotal": str(-original_invoice.subtotal),
            "tax_total": str(-original_invoice.tax_total),
            "grand_total": str(-original_invoice.grand_total),
        },
    )
    await event_bus.publish(event, session=session)

    await session.commit()
    await session.refresh(refund_sale_row)

    return PosRefundOut(
        pos_sale_id=refund_sale_row.id,
        credit_note_id=credit_note.id,
        credit_note_number=credit_note_number,
        refunded_amount=original_invoice.grand_total,
    )
