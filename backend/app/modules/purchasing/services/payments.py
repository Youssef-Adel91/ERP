"""
app/modules/purchasing/services/payments.py — Supplier Payments & Settlement Service

Implements:
  1. create_supplier_payment: Creates a draft SupplierPayment with deterministic SHA-256 hash.
  2. allocate_payment: Allocates payment to a posted VendorBill and calculates realized FX gain/loss (FR-533).
  3. post_supplier_payment: Transitions to POSTED and emits purchase.payment_made outbox event.
"""
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.models.mixins import DocumentState, compute_content_hash
from app.modules.purchasing.exceptions import (
    PaymentAllocationError,
    SupplierPaymentNotFoundError,
    VendorBillNotFoundError,
)
from app.modules.purchasing.models.billing import VendorBill, VendorBillStatus
from app.modules.purchasing.models.payments import (
    PaymentAllocation,
    SupplierPayment,
    SupplierPaymentStatus,
)


async def create_supplier_payment(
    session: AsyncSession,
    supplier_id: UUID | str,
    treasury_id: UUID | str,
    payment_number: str,
    amount: Decimal | str = Decimal("0.0000"),
    payment_date: date | None = None,
    currency: str = "EGP",
    fx_rate: Decimal | str = Decimal("1.000000"),
    allocations_data: list[dict[str, Any]] | None = None,
) -> SupplierPayment:
    """
    Create a new draft SupplierPayment with optional initial bill allocations.
    """
    if isinstance(supplier_id, str):
        supplier_id = UUID(supplier_id)
    if isinstance(treasury_id, str):
        treasury_id = UUID(treasury_id)
    if isinstance(amount, str):
        amount = Decimal(amount)
    if isinstance(fx_rate, str):
        fx_rate = Decimal(fx_rate)
    if payment_date is None:
        payment_date = date.today()

    approvable_payload = {
        "payment_number": payment_number,
        "supplier_id": str(supplier_id),
        "treasury_id": str(treasury_id),
        "payment_date": payment_date.isoformat(),
        "currency": currency,
        "fx_rate": str(fx_rate),
        "amount": str(amount),
    }

    payment = SupplierPayment(
        payment_number=payment_number,
        supplier_id=supplier_id,
        treasury_id=treasury_id,
        payment_date=payment_date,
        currency=currency,
        fx_rate=fx_rate,
        amount=amount,
        fx_gain_loss_amount=Decimal("0.0000"),
        status=SupplierPaymentStatus.DRAFT,
        state=DocumentState.DRAFT,
        content_hash=compute_content_hash(approvable_payload),
    )
    session.add(payment)
    await session.flush()

    if allocations_data:
        for alloc_dict in allocations_data:
            await allocate_payment(
                session=session,
                payment_id=payment.id,
                bill_id=alloc_dict["bill_id"],
                allocated_amount=alloc_dict["allocated_amount"],
            )

    stmt = (
        select(SupplierPayment)
        .where(SupplierPayment.id == payment.id)
        .options(selectinload(SupplierPayment.allocations))
    )
    res = await session.execute(stmt)
    return res.scalar_one()


async def allocate_payment(
    session: AsyncSession,
    payment_id: UUID | str,
    bill_id: UUID | str,
    allocated_amount: Decimal | str,
) -> SupplierPayment:
    """
    Allocate a SupplierPayment against a posted VendorBill.
    Computes Realized FX Gain/Loss (FR-533):
      Base Amount cleared from AP = allocated_amount * bill.fx_rate
      Base Amount paid from Treasury = allocated_amount * payment.fx_rate
      fx_gain_loss_amount = (Base Amount paid - Base Amount cleared)
    """
    if isinstance(payment_id, str):
        payment_id = UUID(payment_id)
    if isinstance(bill_id, str):
        bill_id = UUID(bill_id)
    if isinstance(allocated_amount, str):
        allocated_amount = Decimal(allocated_amount)

    if allocated_amount <= Decimal("0.0000"):
        raise PaymentAllocationError("Allocated amount must be greater than zero.")

    # 1. Fetch SupplierPayment
    stmt = (
        select(SupplierPayment)
        .where(SupplierPayment.id == payment_id)
        .options(selectinload(SupplierPayment.allocations))
    )
    res = await session.execute(stmt)
    payment = res.scalar_one_or_none()
    if not payment:
        raise SupplierPaymentNotFoundError(payment_id)

    if payment.status != SupplierPaymentStatus.DRAFT:
        raise ValueError(
            f"Cannot allocate to SupplierPayment {payment.id}: status is '{payment.status}', expected 'DRAFT'."
        )

    # 2. Fetch VendorBill
    b_stmt = select(VendorBill).where(VendorBill.id == bill_id)
    b_res = await session.execute(b_stmt)
    bill = b_res.scalar_one_or_none()
    if not bill:
        raise VendorBillNotFoundError(bill_id)

    if bill.status != VendorBillStatus.POSTED:
        raise ValueError(
            f"Cannot allocate payment to VendorBill {bill.id}: bill status is '{bill.status}', expected 'POSTED'."
        )

    # 3. Prevent duplicate bill allocation on the same payment
    stmt_existing = select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id)
    res_existing = await session.execute(stmt_existing)
    existing_allocs = res_existing.scalars().all()

    for existing_alloc in existing_allocs:
        if existing_alloc.bill_id == bill.id:
            raise PaymentAllocationError(
                f"VendorBill {bill.id} is already allocated on Payment {payment.id}."
            )

    # 4. Check total allocated amount against payment amount
    existing_allocated = sum(a.allocated_amount for a in existing_allocs)
    new_total_allocated = existing_allocated + allocated_amount
    if payment.amount > Decimal("0.0000") and new_total_allocated > payment.amount:
        raise PaymentAllocationError(
            f"Total allocated amount {new_total_allocated} exceeds payment amount {payment.amount}."
        )
    if payment.amount == Decimal("0.0000"):
        payment.amount = new_total_allocated

    # 5. Create PaymentAllocation
    allocation = PaymentAllocation(
        payment_id=payment.id,
        bill_id=bill.id,
        allocated_amount=allocated_amount,
    )
    session.add(allocation)
    await session.flush()

    # 6. Recalculate FX Gain/Loss across all allocations for this payment
    stmt_allocs = (
        select(PaymentAllocation)
        .where(PaymentAllocation.payment_id == payment.id)
        .options(selectinload(PaymentAllocation.bill))
    )
    res_allocs = await session.execute(stmt_allocs)
    all_allocs = res_allocs.scalars().all()

    total_fx_diff = Decimal("0.0000")
    for alloc in all_allocs:
        bill_obj = alloc.bill
        if not bill_obj:
            b_stmt_single = select(VendorBill).where(VendorBill.id == alloc.bill_id)
            b_res_single = await session.execute(b_stmt_single)
            bill_obj = b_res_single.scalar_one()

        base_cleared = (alloc.allocated_amount * bill_obj.fx_rate).quantize(Decimal("0.0001"))
        base_paid = (alloc.allocated_amount * payment.fx_rate).quantize(Decimal("0.0001"))
        total_fx_diff += base_paid - base_cleared

    payment.fx_gain_loss_amount = total_fx_diff.quantize(Decimal("0.0001"))
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    return payment


async def post_supplier_payment(
    session: AsyncSession,
    payment_id: UUID | str,
) -> SupplierPayment:
    """
    Post a SupplierPayment to AP and Treasury/Bank.
    Transitions status to POSTED and emits purchase.payment_made outbox domain event.
    """
    if isinstance(payment_id, str):
        payment_id = UUID(payment_id)

    stmt = (
        select(SupplierPayment)
        .where(SupplierPayment.id == payment_id)
        .options(
            selectinload(SupplierPayment.allocations).selectinload(PaymentAllocation.bill)
        )
    )
    res = await session.execute(stmt)
    payment = res.scalar_one_or_none()
    if not payment:
        raise SupplierPaymentNotFoundError(payment_id)

    if payment.status != SupplierPaymentStatus.DRAFT:
        raise ValueError(
            f"Cannot post SupplierPayment {payment.id}: status is '{payment.status}', expected 'DRAFT'."
        )

    stmt_allocs = (
        select(PaymentAllocation)
        .where(PaymentAllocation.payment_id == payment.id)
        .options(selectinload(PaymentAllocation.bill))
    )
    res_allocs = await session.execute(stmt_allocs)
    all_allocs = res_allocs.scalars().all()

    if not all_allocs and payment.amount <= Decimal("0.0000"):
        raise ValueError("Cannot post SupplierPayment with zero amount and no allocations.")

    payment.status = SupplierPaymentStatus.POSTED
    payment.state = DocumentState.POSTED
    session.add(payment)
    await session.flush()

    try:
        from app.core.db.context import current_tenant

        tenant_id = current_tenant.get()
    except (ImportError, Exception):
        tenant_id = "system"

    base_amount_paid = Decimal("0.0000")
    base_amount_cleared = Decimal("0.0000")
    allocations_payload = []

    for alloc in all_allocs:
        bill_obj = alloc.bill
        if not bill_obj:
            b_stmt = select(VendorBill).where(VendorBill.id == alloc.bill_id)
            b_res = await session.execute(b_stmt)
            bill_obj = b_res.scalar_one()

        b_cleared = (alloc.allocated_amount * bill_obj.fx_rate).quantize(Decimal("0.0001"))
        b_paid = (alloc.allocated_amount * payment.fx_rate).quantize(Decimal("0.0001"))
        base_amount_cleared += b_cleared
        base_amount_paid += b_paid

        allocations_payload.append(
            {
                "allocation_id": str(alloc.id),
                "bill_id": str(alloc.bill_id),
                "bill_number": bill_obj.bill_number,
                "allocated_amount": str(alloc.allocated_amount),
                "bill_fx_rate": str(bill_obj.fx_rate),
                "base_amount_cleared": str(b_cleared),
                "base_amount_paid": str(b_paid),
                "fx_gain_loss": str(b_paid - b_cleared),
            }
        )

    if not all_allocs:
        base_amount_paid = (payment.amount * payment.fx_rate).quantize(Decimal("0.0001"))
        base_amount_cleared = base_amount_paid

    event_bus = get_event_bus()
    event = DomainEvent(
        event_type="purchase.payment_made",
        tenant_id=str(tenant_id),
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "supplier_id": str(payment.supplier_id),
            "treasury_id": str(payment.treasury_id),
            "payment_date": payment.payment_date.isoformat(),
            "currency": payment.currency,
            "fx_rate": str(payment.fx_rate),
            "amount": str(payment.amount),
            "fx_gain_loss_amount": str(payment.fx_gain_loss_amount),
            "base_amount_paid": str(base_amount_paid),
            "base_amount_cleared": str(base_amount_cleared),
            "allocations": allocations_payload,
        },
    )
    await event_bus.publish(event, session=session)

    await session.refresh(payment)
    return payment
