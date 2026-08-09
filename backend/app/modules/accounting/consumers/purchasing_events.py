"""
app/modules/accounting/consumers/purchasing_events.py — Purchasing Event Consumers for Accounting GL Bridge

Translates purchasing domain events into strict Double-Entry Journal Entries:
  1. purchase.goods_received -> DR Inventory Asset, CR GRNI Accrual (Goods Received Not Invoiced)
  2. purchase.bill_posted -> DR GRNI Accrual, DR Input VAT Receivable (if applicable), CR Accounts Payable (AP)

Guarantees idempotency: any duplicated event with an existing reference_id is skipped.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.accounting.models.core import Account, JournalEntry, JournalEntryStatus
from app.modules.accounting.services.journal import create_journal_entry
from app.modules.accounting.services.mappings import (
    AccountMappingKey,
    get_default_account_id,
)

logger = logging.getLogger(__name__)
event_bus = get_event_bus()


async def _is_already_journaled(
    session: AsyncSession,
    reference_id: UUID | None,
    reference: str | None = None,
) -> JournalEntry | None:
    """Check if a JournalEntry has already been created for this reference_id / reference."""
    if reference_id is not None:
        stmt = select(JournalEntry).where(JournalEntry.reference_id == reference_id)
        result = await session.execute(stmt)
        entry = result.scalars().first()
        if entry is not None:
            return entry

    if reference is not None:
        stmt = select(JournalEntry).where(JournalEntry.reference == reference)
        result = await session.execute(stmt)
        entry = result.scalars().first()
        if entry is not None:
            return entry

    return None


async def process_grn_posted(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> JournalEntry | None:
    """
    Process purchase.goods_received event and generate a balanced JournalEntry:
      DR  Inventory Asset
      CR  GRNI Accrual (Goods Received Not Invoiced)
    """
    grn_id_str = payload.get("grn_id") or payload.get("id")
    if not grn_id_str:
        raise ValueError("purchase.goods_received payload missing 'grn_id' or 'id'")

    grn_id = UUID(str(grn_id_str))
    grn_number = str(payload.get("grn_number", f"GRN-{grn_id_str[:8]}"))
    reference = f"GRN-{grn_number}"

    existing_entry = await _is_already_journaled(
        session, reference_id=grn_id, reference=reference
    )
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for GRN '%s' (entry_id=%s). Skipping.",
            grn_number,
            existing_entry.id,
        )
        return existing_entry

    inventory_id = await get_default_account_id(
        session, AccountMappingKey.INVENTORY_ASSET
    )
    grni_id = await get_default_account_id(session, AccountMappingKey.GRNI_ACCRUAL)

    total_value = Decimal("0.0000")
    lines_data = payload.get("lines", [])
    for line in lines_data:
        qty = Decimal(str(line.get("qty_received", "0")))
        cost = Decimal(
            str(
                line.get("unit_cost_base")
                or line.get("unit_cost_estimated")
                or "0.0000"
            )
        )
        total_value += qty * cost

    if total_value <= Decimal("0"):
        logger.warning(
            "GRN '%s' has 0 total value; skipping GL journal creation.",
            grn_number,
        )
        return None

    lines = [
        {
            "account_id": inventory_id,
            "debit": total_value,
            "credit": Decimal("0.0000"),
            "description": f"Inventory Asset — GRN {grn_number}",
        },
        {
            "account_id": grni_id,
            "debit": Decimal("0.0000"),
            "credit": total_value,
            "description": f"GRNI Accrual — GRN {grn_number}",
        },
    ]

    entry = await create_journal_entry(
        session=session,
        reference=reference,
        description=f"Automated GL entry for Goods Receipt {grn_number}",
        lines=lines,
        reference_id=grn_id,
        reference_type="purchase.goods_received",
        source_type="purchase.goods_received",
        source_id=grn_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for purchase.goods_received (%s) | Amount=%s",
        entry.id,
        reference,
        total_value,
    )
    return entry


async def process_bill_posted(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> JournalEntry | None:
    """
    Process purchase.bill_posted event and generate a balanced JournalEntry:
      DR  GRNI Accrual         (subtotal - clears liability from GRN)
      DR  Input VAT Receivable (tax_total - if applicable)
      CR  Accounts Payable     (total_amount = subtotal + tax_total)
    """
    bill_id_str = payload.get("bill_id") or payload.get("id")
    if not bill_id_str:
        raise ValueError("purchase.bill_posted payload missing 'bill_id' or 'id'")

    bill_id = UUID(str(bill_id_str))
    bill_number = str(payload.get("bill_number", f"BILL-{bill_id_str[:8]}"))
    reference = f"BILL-{bill_number}"

    existing_entry = await _is_already_journaled(
        session, reference_id=bill_id, reference=reference
    )
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for Bill '%s' (entry_id=%s). Skipping.",
            bill_number,
            existing_entry.id,
        )
        return existing_entry

    grni_id = await get_default_account_id(session, AccountMappingKey.GRNI_ACCRUAL)
    ap_id = await get_default_account_id(session, AccountMappingKey.ACCOUNTS_PAYABLE)
    vat_id = await get_default_account_id(
        session, AccountMappingKey.INPUT_VAT_RECEIVABLE
    )

    subtotal = abs(Decimal(str(payload.get("subtotal", "0"))))
    tax_total = abs(Decimal(str(payload.get("tax_total", "0"))))
    total_amount = abs(Decimal(str(payload.get("total_amount", "0"))))

    if subtotal == Decimal("0") and total_amount > Decimal("0"):
        subtotal = total_amount - tax_total

    if total_amount <= Decimal("0"):
        logger.warning(
            "Bill '%s' has 0 total amount; skipping GL journal creation.",
            bill_number,
        )
        return None

    lines = []
    if subtotal > Decimal("0"):
        lines.append(
            {
                "account_id": grni_id,
                "debit": subtotal,
                "credit": Decimal("0.0000"),
                "description": f"GRNI Clearing — Bill {bill_number}",
            }
        )
    if tax_total > Decimal("0"):
        lines.append(
            {
                "account_id": vat_id,
                "debit": tax_total,
                "credit": Decimal("0.0000"),
                "description": f"Input VAT — Bill {bill_number}",
            }
        )
    lines.append(
        {
            "account_id": ap_id,
            "debit": Decimal("0.0000"),
            "credit": total_amount,
            "description": f"Accounts Payable — Bill {bill_number}",
        }
    )

    entry = await create_journal_entry(
        session=session,
        reference=reference,
        description=f"Automated GL entry for Vendor Bill {bill_number}",
        lines=lines,
        reference_id=bill_id,
        reference_type="purchase.bill_posted",
        source_type="purchase.bill_posted",
        source_id=bill_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for purchase.bill_posted (%s) | AP=%s",
        entry.id,
        reference,
        total_amount,
    )
    return entry


@event_bus.subscribe("purchase.goods_received")
async def handle_grn_posted(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for purchase.goods_received."""
    if session is not None:
        return await process_grn_posted(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_grn_posted(sess, event.payload, str(event.event_id))


@event_bus.subscribe("purchase.bill_posted")
async def handle_bill_posted(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for purchase.bill_posted."""
    if session is not None:
        return await process_bill_posted(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_bill_posted(sess, event.payload, str(event.event_id))


async def process_landed_cost_allocated(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> JournalEntry | None:
    """
    Process purchase.landed_cost_allocated event and generate a balanced JournalEntry:
      DR  Inventory Asset (capitalizing landed cost into stock valuation)
      CR  Landed Cost Clearing (liability/clearing account to settle against freight/customs bills)
    """
    shipment_id_str = payload.get("shipment_id") or payload.get("id")
    if not shipment_id_str:
        raise ValueError("purchase.landed_cost_allocated payload missing 'shipment_id' or 'id'")

    shipment_id = UUID(str(shipment_id_str))
    shipment_ref = str(payload.get("shipment_ref", f"SHP-{shipment_id_str[:8]}"))
    reference = f"SHP-{shipment_ref}"

    existing_entry = await _is_already_journaled(
        session, reference_id=shipment_id, reference=reference
    )
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for Shipment '%s' (entry_id=%s). Skipping.",
            shipment_ref,
            existing_entry.id,
        )
        return existing_entry

    inventory_id = await get_default_account_id(
        session, AccountMappingKey.INVENTORY_ASSET
    )
    clearing_id = await get_default_account_id(
        session, AccountMappingKey.LANDED_COST_CLEARING
    )

    total_landed_cost = Decimal(str(payload.get("total_landed_cost", "0.0000"))).quantize(
        Decimal("0.0001")
    )
    if total_landed_cost <= Decimal("0.0000"):
        logger.info(
            "Skipping GL entry for Shipment '%s': total_landed_cost is 0.",
            shipment_ref,
        )
        return None

    lines = [
        {
            "account_id": inventory_id,
            "debit": total_landed_cost,
            "credit": Decimal("0.0000"),
            "description": f"Inventory Landed Cost Capitalization — {shipment_ref}",
        },
        {
            "account_id": clearing_id,
            "debit": Decimal("0.0000"),
            "credit": total_landed_cost,
            "description": f"Landed Cost Clearing — {shipment_ref}",
        },
    ]

    entry = await create_journal_entry(
        session=session,
        reference=reference,
        description=f"Automated GL entry for Landed Cost Allocation — Shipment {shipment_ref}",
        lines=lines,
        reference_id=shipment_id,
        reference_type="purchase.landed_cost_allocated",
        source_type="purchase.landed_cost_allocated",
        source_id=shipment_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for purchase.landed_cost_allocated (%s) | Amount=%s",
        entry.id,
        reference,
        total_landed_cost,
    )
    return entry


@event_bus.subscribe("purchase.landed_cost_allocated")
async def handle_landed_cost_allocated(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for purchase.landed_cost_allocated."""
    if session is not None:
        return await process_landed_cost_allocated(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_landed_cost_allocated(sess, event.payload, str(event.event_id))


async def process_payment_made(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> JournalEntry | None:
    """
    Process purchase.payment_made event and generate a balanced JournalEntry:
      DR  Accounts Payable        (Base Amount cleared)
      CR  Treasury / Bank         (Base Amount paid)
      DR (if Loss) or CR (if Gain) FX Variance Expense (Realized FX difference)
    """
    payment_id_str = payload.get("payment_id") or payload.get("id")
    if not payment_id_str:
        raise ValueError("purchase.payment_made payload missing 'payment_id' or 'id'")

    payment_id = UUID(str(payment_id_str))
    payment_number = str(payload.get("payment_number", f"PAY-{payment_id_str[:8]}"))
    reference = f"PAY-{payment_number}"

    existing_entry = await _is_already_journaled(
        session, reference_id=payment_id, reference=reference
    )
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for Payment '%s' (entry_id=%s). Skipping.",
            payment_number,
            existing_entry.id,
        )
        return existing_entry

    ap_id = await get_default_account_id(session, AccountMappingKey.ACCOUNTS_PAYABLE)
    fx_expense_id = await get_default_account_id(
        session, AccountMappingKey.FX_VARIANCE_EXPENSE
    )

    # Check if treasury_id refers to an existing Account in DB
    treasury_id_str = payload.get("treasury_id")
    treasury_account_id = None
    if treasury_id_str:
        try:
            stmt = select(Account).where(Account.id == UUID(str(treasury_id_str)))
            res = await session.execute(stmt)
            t_acc = res.scalar_one_or_none()
            if t_acc:
                treasury_account_id = t_acc.id
        except (ValueError, Exception):
            pass

    if not treasury_account_id:
        treasury_account_id = await get_default_account_id(
            session, AccountMappingKey.CASH_AND_BANKS
        )

    base_amount_cleared = Decimal(str(payload.get("base_amount_cleared", "0.0000"))).quantize(
        Decimal("0.0001")
    )
    base_amount_paid = Decimal(str(payload.get("base_amount_paid", "0.0000"))).quantize(
        Decimal("0.0001")
    )

    fx_gain_loss = (base_amount_paid - base_amount_cleared).quantize(Decimal("0.0001"))

    if base_amount_paid <= Decimal("0.0000") and base_amount_cleared <= Decimal("0.0000"):
        logger.warning(
            "Payment '%s' has 0 total amount; skipping GL journal creation.",
            payment_number,
        )
        return None

    lines = []
    if base_amount_cleared > Decimal("0.0000"):
        lines.append(
            {
                "account_id": ap_id,
                "debit": base_amount_cleared,
                "credit": Decimal("0.0000"),
                "description": f"Accounts Payable Clearing — Payment {payment_number}",
            }
        )

    if base_amount_paid > Decimal("0.0000"):
        lines.append(
            {
                "account_id": treasury_account_id,
                "debit": Decimal("0.0000"),
                "credit": base_amount_paid,
                "description": f"Treasury / Bank Payment — Payment {payment_number}",
            }
        )

    if fx_gain_loss > Decimal("0.0000"):
        # Realized FX Loss -> DEBIT FX Variance Expense
        lines.append(
            {
                "account_id": fx_expense_id,
                "debit": fx_gain_loss,
                "credit": Decimal("0.0000"),
                "description": f"Realized FX Loss — Payment {payment_number}",
            }
        )
    elif fx_gain_loss < Decimal("0.0000"):
        # Realized FX Gain -> CREDIT FX Variance Expense
        lines.append(
            {
                "account_id": fx_expense_id,
                "debit": Decimal("0.0000"),
                "credit": abs(fx_gain_loss),
                "description": f"Realized FX Gain — Payment {payment_number}",
            }
        )

    entry = await create_journal_entry(
        session=session,
        reference=reference,
        description=f"Automated GL entry for Supplier Payment {payment_number}",
        lines=lines,
        reference_id=payment_id,
        reference_type="purchase.payment_made",
        source_type="purchase.payment_made",
        source_id=payment_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for purchase.payment_made (%s) | Paid=%s | Cleared=%s | FX=%s",
        entry.id,
        reference,
        base_amount_paid,
        base_amount_cleared,
        fx_gain_loss,
    )
    return entry


@event_bus.subscribe("purchase.payment_made")
async def handle_payment_made(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for purchase.payment_made."""
    if session is not None:
        return await process_payment_made(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_payment_made(sess, event.payload, str(event.event_id))
