"""
app/modules/sales/services/payments.py — Customer (Sales) Payments Service

Wave 3 item 1. Mirrors app/modules/purchasing/services/payments.py's shape
(create DRAFT -> allocate against posted documents -> post, emitting a
domain event picked up by the GL Bridge) but for Accounts Receivable:

  1. create_sales_payment: creates a DRAFT SalesPayment, optionally with
     initial invoice allocations.
  2. allocate_sales_payment: allocates a DRAFT payment against a POSTED (or
     already-partially-paid) SalesInvoice — rejects over-allocation past the
     invoice's own outstanding balance.
  3. post_sales_payment: DRAFT -> POSTED, emits `sales.payment_received` for
     the accounting GL Bridge, and flips any invoice whose allocated total
     now covers its grand_total to SalesInvoiceStatus.PAID (this is the
     first and only writer of that enum value — it already existed on
     SalesInvoiceStatus but nothing transitioned into it before this).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.models.mixins import DocumentState, compute_content_hash
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.sales.models.payments import (
    SalesPayment,
    SalesPaymentAllocation,
    SalesPaymentStatus,
)


async def _invoice_outstanding_balance(session: AsyncSession, invoice: SalesInvoice) -> Decimal:
    """
    grand_total minus the sum of allocated_amount across every allocation
    belonging to a non-CANCELLED SalesPayment already POSTED against it.
    DRAFT payments don't reserve balance — only POSTED ones are real money.
    """
    stmt = (
        select(SalesPaymentAllocation)
        .where(SalesPaymentAllocation.invoice_id == invoice.id)
        .options(selectinload(SalesPaymentAllocation.payment))
    )
    res = await session.execute(stmt)
    allocations = res.scalars().all()
    already_paid = sum(
        (a.allocated_amount for a in allocations if a.payment and a.payment.status == SalesPaymentStatus.POSTED),
        Decimal("0.0000"),
    )
    return invoice.grand_total - already_paid


async def create_sales_payment(
    session: AsyncSession,
    contact_id: UUID | str,
    payment_number: str,
    amount: Decimal | str = Decimal("0.0000"),
    payment_date: date | None = None,
    payment_method: str = "CASH",
    reference: str | None = None,
    notes: str | None = None,
    currency: str = "EGP",
    treasury_id: UUID | str | None = None,
    created_by: UUID | None = None,
    allocations_data: list[dict] | None = None,
) -> SalesPayment:
    """Create a new DRAFT SalesPayment, optionally with initial invoice allocations."""
    if isinstance(contact_id, str):
        contact_id = UUID(contact_id)
    if isinstance(treasury_id, str) and treasury_id:
        treasury_id = UUID(treasury_id)
    if isinstance(amount, str):
        amount = Decimal(amount)
    if payment_date is None:
        payment_date = date.today()

    approvable_payload = {
        "payment_number": payment_number,
        "contact_id": str(contact_id),
        "payment_date": payment_date.isoformat(),
        "currency": currency,
        "amount": str(amount),
    }

    payment = SalesPayment(
        payment_number=payment_number,
        contact_id=contact_id,
        treasury_id=treasury_id or None,
        payment_date=payment_date,
        payment_method=payment_method,
        reference=reference,
        notes=notes,
        currency=currency,
        amount=amount,
        status=SalesPaymentStatus.DRAFT,
        state=DocumentState.DRAFT,
        content_hash=compute_content_hash(approvable_payload),
        created_by=created_by,
    )
    session.add(payment)
    await session.flush()

    if allocations_data:
        for alloc in allocations_data:
            await allocate_sales_payment(
                session=session,
                payment_id=payment.id,
                invoice_id=alloc["invoice_id"],
                allocated_amount=alloc["allocated_amount"],
            )

    stmt = (
        select(SalesPayment)
        .where(SalesPayment.id == payment.id)
        .options(selectinload(SalesPayment.allocations))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def allocate_sales_payment(
    session: AsyncSession,
    payment_id: UUID | str,
    invoice_id: UUID | str,
    allocated_amount: Decimal | str,
) -> SalesPayment:
    """Allocate a DRAFT SalesPayment against a POSTED SalesInvoice."""
    if isinstance(payment_id, str):
        payment_id = UUID(payment_id)
    if isinstance(invoice_id, str):
        invoice_id = UUID(invoice_id)
    if isinstance(allocated_amount, str):
        allocated_amount = Decimal(allocated_amount)

    if allocated_amount <= Decimal("0.0000"):
        raise ValueError("Allocated amount must be greater than zero.")

    stmt = (
        select(SalesPayment)
        .where(SalesPayment.id == payment_id)
        .options(selectinload(SalesPayment.allocations))
    )
    res = await session.execute(stmt)
    payment = res.scalar_one_or_none()
    if not payment:
        raise ValueError(f"Sales payment not found: {payment_id}")

    if payment.status != SalesPaymentStatus.DRAFT:
        raise ValueError(
            f"Cannot allocate SalesPayment {payment.id}: status is '{payment.status}', expected 'DRAFT'."
        )

    invoice_stmt = select(SalesInvoice).where(SalesInvoice.id == invoice_id)
    invoice_res = await session.execute(invoice_stmt)
    invoice = invoice_res.scalar_one_or_none()
    if not invoice:
        raise ValueError(f"Sales invoice not found: {invoice_id}")

    if invoice.status not in (SalesInvoiceStatus.POSTED,):
        raise ValueError(
            f"Cannot allocate payment to invoice {invoice.id}: invoice status is "
            f"'{invoice.status}', expected 'POSTED' (unpaid)."
        )

    # Prevent duplicate invoice allocation on the same payment.
    for existing in payment.allocations:
        if existing.invoice_id == invoice.id:
            raise ValueError(f"Invoice {invoice.id} is already allocated on payment {payment.id}.")

    outstanding = await _invoice_outstanding_balance(session, invoice)
    if allocated_amount > outstanding:
        raise ValueError(
            f"Allocated amount {allocated_amount} exceeds invoice {invoice.invoice_number}'s "
            f"outstanding balance of {outstanding}."
        )

    existing_total = sum((a.allocated_amount for a in payment.allocations), Decimal("0.0000"))
    new_total = existing_total + allocated_amount
    if payment.amount > Decimal("0.0000") and new_total > payment.amount:
        raise ValueError(
            f"Total allocated amount {new_total} exceeds payment amount {payment.amount}."
        )
    if payment.amount == Decimal("0.0000"):
        payment.amount = new_total

    allocation = SalesPaymentAllocation(
        payment_id=payment.id,
        invoice_id=invoice.id,
        allocated_amount=allocated_amount,
    )
    session.add(allocation)
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    return payment


async def post_sales_payment(
    session: AsyncSession,
    payment_id: UUID | str,
) -> SalesPayment:
    """
    Post a DRAFT SalesPayment: DRAFT -> POSTED, flips any now-fully-paid
    invoice to PAID, and emits `sales.payment_received` for the GL Bridge.
    """
    if isinstance(payment_id, str):
        payment_id = UUID(payment_id)

    stmt = (
        select(SalesPayment)
        .where(SalesPayment.id == payment_id)
        .options(
            selectinload(SalesPayment.allocations).selectinload(SalesPaymentAllocation.invoice)
        )
    )
    res = await session.execute(stmt)
    payment = res.scalar_one_or_none()
    if not payment:
        raise ValueError(f"Sales payment not found: {payment_id}")

    if payment.status != SalesPaymentStatus.DRAFT:
        raise ValueError(
            f"Cannot post SalesPayment {payment.id}: status is '{payment.status}', expected 'DRAFT'."
        )

    if not payment.allocations and payment.amount <= Decimal("0.0000"):
        raise ValueError("Cannot post a sales payment with zero amount and no invoice allocations.")

    payment.status = SalesPaymentStatus.POSTED
    payment.state = DocumentState.POSTED
    session.add(payment)
    await session.flush()

    # Flip any invoice that is now fully covered to PAID. Re-check against
    # the DB (not just this payment's allocations) since a customer can pay
    # off the remainder of one invoice across several separate payments.
    allocations_payload = []
    for alloc in payment.allocations:
        invoice = alloc.invoice
        if invoice is None:
            invoice = await session.get(SalesInvoice, alloc.invoice_id)
        remaining = await _invoice_outstanding_balance(session, invoice)
        if remaining <= Decimal("0.0000") and invoice.status == SalesInvoiceStatus.POSTED:
            invoice.status = SalesInvoiceStatus.PAID
            session.add(invoice)
        allocations_payload.append(
            {
                "allocation_id": str(alloc.id),
                "invoice_id": str(alloc.invoice_id),
                "invoice_number": invoice.invoice_number,
                "allocated_amount": str(alloc.allocated_amount),
            }
        )
    await session.flush()

    try:
        from app.core.db.context import current_tenant

        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        tenant_id = "system"

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="sales.payment_received",
        tenant_id=str(tenant_id),
        payload={
            "id": str(payment.id),
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "contact_id": str(payment.contact_id),
            "treasury_id": str(payment.treasury_id) if payment.treasury_id else None,
            "payment_date": payment.payment_date.isoformat(),
            "payment_method": payment.payment_method,
            "currency": payment.currency,
            "amount": str(payment.amount),
            "allocations": allocations_payload,
        },
    )
    await event_bus.publish(event, session=session)

    await session.refresh(payment)
    return payment
