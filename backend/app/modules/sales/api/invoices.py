"""
app/modules/sales/api/invoices.py — Sales Invoice REST API

The modules/sales domain layer (models/invoice.py + services/invoicing.py)
already existed fully written but had zero HTTP exposure. This adds the
missing router, calling into the real service functions rather than
reimplementing their logic inline (same rule as approvals/api.py →
approval_engine.py).

Contract note vs. the currently-live app/plugins/sales router: the live
plugin creates a SalesInvoice directly from arbitrary lines (customer_id +
item lines), already CONFIRMED, in one step. modules/sales originally only
supported generating a DRAFT invoice FROM an existing FULFILLED/
PARTIALLY_FULFILLED SalesOrder (generate_invoice_from_order()) — no ad-hoc
path. That's correct for physical-goods flows but broke service verticals
(Hospitality folio checkout, Vehicle Rental agreement close-out) that bill
directly with no preceding SalesOrder. So SalesInvoice.order_id was made
nullable and services/invoicing.create_adhoc_invoice() was added alongside
generate_invoice_from_order(); this endpoint now accepts EITHER an `order_id`
(order-based) OR a `contact_id` + `lines` (ad-hoc), mutually exclusive.
The "confirm" action's real name in the service layer is `post_invoice`,
which flips the invoice DRAFT -> POSTED, conditionally flips a linked
SalesOrder to INVOICED (skipped entirely for ad-hoc invoices — there is no
order to advance), and publishes the `sales.invoice_posted` DomainEvent
inside the same DB transaction (verified against
app/modules/accounting/consumers/events.py's `process_invoice_posted`,
which reads `payload["id"]`/`payload["invoice_id"]` plus subtotal/tax_total/
grand_total — exactly what post_invoice publishes, order_id included as
nullable). So calling this endpoint drives the real GL posting end to end
for both flows.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.database import get_redis, get_tenant_db
from app.core.idempotency import IdempotencyKey, get_cached_resource_id, store_idempotent_result
from app.modules.contacts.models import Contact
from app.modules.inventory.models.core import Item
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceLine, SalesInvoiceStatus
from app.modules.sales.services.invoicing import (
    create_adhoc_invoice,
    generate_invoice_from_order,
    post_invoice,
)
from app.modules.sales.services.pdf_builder import build_sales_invoice_pdf
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/sales/invoices", tags=["Sales - Invoices"])


class SalesInvoiceLineOut(BaseModel):
    id: UUID
    item_id: UUID
    variant_id: UUID | None = None
    uom_id: UUID | None = None
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal
    tax_rate: Decimal
    tax_amount: Decimal

    model_config = {"from_attributes": True}


class SalesInvoiceDetail(BaseModel):
    """
    GET /{invoice_id}-only response schema.

    `SalesInvoice` is a SQLModel *table* model — its `lines` relationship
    (models/invoice.py) is declared via `Relationship()`, not `Field()`, and
    SQLModel does not include `Relationship()`-declared attributes in the
    Pydantic schema it generates for table models. So even though this
    endpoint already eager-loads `.lines` (`selectinload`, and the
    relationship itself is `lazy="selectin"`) and its own docstring/summary
    says "includes lines", the response actually always dropped them
    silently — confirmed live (`GET /sales/invoices/{id}` on a real invoice
    with a real line returned no `lines` key at all). Needed now because the
    Sales Returns (RMA) UI has to know each line's
    `id`/`item_id`/`qty`/`unit_price` to build a return request
    (`original_invoice_line_id` per line) — there was no way to get that
    from this API before. Scoped to this one endpoint only (not the list
    endpoint) so nothing else's response shape changes.

    A plain BaseModel, NOT `class SalesInvoiceDetail(SalesInvoice): ...` —
    subclassing a SQLModel `table=True` class for a response-only variant
    crashed the app at import time (SQLModel/SQLAlchemy tries to register
    the subclass as a second mapped class for the same table), confirmed
    live via the backend process dying on reload with no further log output
    once that version of this file was deployed. Every field below mirrors
    `SalesInvoice`'s own fields (DocumentLifecycleMixin + TenantBase +
    invoice.py) so the response shape for everything except `lines` is
    unchanged from before.
    """

    model_config = {"from_attributes": True}

    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    updated_by: UUID | None = None
    deleted_at: datetime | None = None
    state: str
    content_hash: str | None = None
    submitted_at: datetime | None = None
    submitted_by: UUID | None = None
    approved_at: datetime | None = None
    posted_at: datetime | None = None
    reversal_of_id: UUID | None = None
    invoice_number: str
    order_id: UUID | None = None
    contact_id: UUID
    status: SalesInvoiceStatus
    issue_date: date
    due_date: date
    currency: str
    subtotal: Decimal
    tax_total: Decimal
    grand_total: Decimal
    lines: list[SalesInvoiceLineOut] = []


class AdhocInvoiceLineIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    uom_id: UUID | None = None
    qty: Decimal
    unit_price: Decimal
    tax_rate: Decimal | None = None


class SalesInvoiceCreateRequest(BaseModel):
    # Order-based path (physical-goods flow):
    order_id: UUID | None = None
    # Ad-hoc path (service verticals — Hospitality, Rental — or any manual
    # invoice with no preceding SalesOrder):
    contact_id: UUID | None = None
    lines: list[AdhocInvoiceLineIn] | None = None
    currency: str = "EGP"

    invoice_number: str | None = None
    due_date: date | None = None
    default_tax_rate: Decimal = Decimal("0.1400")

    @model_validator(mode="after")
    def _exactly_one_path(self) -> "SalesInvoiceCreateRequest":
        has_order = self.order_id is not None
        has_adhoc = self.contact_id is not None or self.lines is not None
        if has_order and has_adhoc:
            raise ValueError("Provide either order_id OR contact_id+lines, not both.")
        if not has_order and not has_adhoc:
            raise ValueError("Provide either order_id (order-based) or contact_id+lines (ad-hoc).")
        if has_adhoc and (self.contact_id is None or not self.lines):
            raise ValueError("Ad-hoc invoices require both contact_id and at least one line.")
        return self


@router.post(
    "",
    response_model=SalesInvoice,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT sales invoice — from a fulfilled sales order, or ad-hoc",
)
async def create_invoice(
    data: SalesInvoiceCreateRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    redis: aioredis.Redis = Depends(get_redis),
    idempotency_key: str | None = IdempotencyKey,
) -> SalesInvoice:
    # Idempotency: a client-supplied Idempotency-Key header lets a retried
    # (e.g. network-retried or double-clicked) request return the invoice
    # already created by the first attempt instead of creating a duplicate.
    cached_id = await get_cached_resource_id(
        redis,
        tenant_id=current_user.tenant_id,
        endpoint="sales.invoices.create",
        idempotency_key=idempotency_key,
    )
    if cached_id is not None:
        existing = await session.get(SalesInvoice, cached_id)
        if existing is not None:
            return existing

    try:
        if data.order_id is not None:
            invoice = await generate_invoice_from_order(
                session=session,
                order_id=data.order_id,
                invoice_number=data.invoice_number,
                due_date=data.due_date,
                default_tax_rate=data.default_tax_rate,
            )
        else:
            invoice = await create_adhoc_invoice(
                session=session,
                contact_id=data.contact_id,  # type: ignore[arg-type]
                lines=[line.model_dump(exclude_none=True) for line in data.lines],  # type: ignore[union-attr]
                invoice_number=data.invoice_number,
                due_date=data.due_date,
                currency=data.currency,
                default_tax_rate=data.default_tax_rate,
            )
        await session.commit()
        await store_idempotent_result(
            redis,
            tenant_id=current_user.tenant_id,
            endpoint="sales.invoices.create",
            idempotency_key=idempotency_key,
            resource_id=invoice.id,
        )
        return invoice
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get(
    "",
    response_model=list[SalesInvoice],
    summary="List sales invoices",
)
async def list_invoices(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    status_filter: SalesInvoiceStatus | None = Query(default=None, alias="status"),
    contact_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SalesInvoice]:
    q = select(SalesInvoice)
    if status_filter:
        q = q.where(SalesInvoice.status == status_filter)
    if contact_id:
        q = q.where(SalesInvoice.contact_id == contact_id)
    q = q.order_by(SalesInvoice.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(q)
    return list(result.scalars().all())


@router.get(
    "/{invoice_id}",
    response_model=SalesInvoiceDetail,
    summary="Get a sales invoice by ID (includes lines)",
)
async def get_invoice(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesInvoice:
    result = await session.execute(
        select(SalesInvoice)
        .where(SalesInvoice.id == invoice_id)
        .options(selectinload(SalesInvoice.lines))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Sales invoice '{invoice_id}' not found.")
    return invoice


@router.get(
    "/{invoice_id}/pdf",
    summary="Download a printable PDF for a sales invoice",
)
async def get_invoice_pdf(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> Response:
    """
    Renders the invoice via app.modules.sales.services.pdf_builder,
    resolving contact_id -> name and each line's item_id -> name first
    (that builder takes plain data in, no DB access of its own — see its
    module docstring). Available for any invoice regardless of status
    (DRAFT included) so a merchant can preview/print before posting.
    """
    result = await session.execute(
        select(SalesInvoice)
        .where(SalesInvoice.id == invoice_id)
        .options(selectinload(SalesInvoice.lines))
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Sales invoice '{invoice_id}' not found.")

    contact = await session.get(Contact, invoice.contact_id)
    contact_name = contact.name if contact else "-"

    item_ids = [invoice_line.item_id for invoice_line in invoice.lines]
    items_by_id: dict[UUID, str] = {}
    if item_ids:
        items_result = await session.execute(select(Item).where(Item.id.in_(item_ids)))
        items_by_id = {item.id: item.name for item in items_result.scalars().all()}

    pdf_bytes = build_sales_invoice_pdf(
        invoice_number=invoice.invoice_number,
        status=invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status),
        issue_date=invoice.issue_date.isoformat(),
        due_date=invoice.due_date.isoformat(),
        currency=invoice.currency,
        contact_name=contact_name,
        subtotal=invoice.subtotal,
        tax_total=invoice.tax_total,
        grand_total=invoice.grand_total,
        lines=[
            {
                "item_name": items_by_id.get(invoice_line.item_id, str(invoice_line.item_id)),
                "qty": invoice_line.qty,
                "unit_price": invoice_line.unit_price,
                "line_total": invoice_line.line_total,
            }
            for invoice_line in invoice.lines
        ],
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="invoice-{invoice.invoice_number}.pdf"'},
    )


@router.post(
    "/{invoice_id}/post",
    response_model=SalesInvoice,
    summary="Post a DRAFT invoice (DRAFT -> POSTED, order -> INVOICED, publishes sales.invoice_posted)",
)
async def post_sales_invoice(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SalesInvoice:
    try:
        invoice = await post_invoice(session=session, invoice_id=invoice_id)
        await session.commit()
        return invoice
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc
