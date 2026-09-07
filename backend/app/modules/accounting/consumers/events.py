"""
app/modules/accounting/consumers/events.py — Automated Financial Event Consumers (The GL Bridge)

Translates operational Outbox domain events into strict Double-Entry Journal Entries:
  1. sales.invoice_posted -> DR Accounts Receivable, CR Sales Revenue, CR Sales Tax Payable
  2. sales.credit_note_posted -> CR Accounts Receivable, DR Sales Revenue, DR Sales Tax Payable
  3. inventory.stock_take_posted -> DR/CR Inventory Asset vs Stock Variance Expense

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
from app.modules.accounting.models.core import JournalEntry, JournalEntryStatus
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


# ── 1. sales.invoice_posted ───────────────────────────────────────────────────


async def process_invoice_posted(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> JournalEntry | None:
    """
    Process sales.invoice_posted event and generate a balanced JournalEntry:
      DR  Accounts Receivable   (grand_total)
      CR  Sales Revenue         (subtotal)
      CR  Sales Tax Payable     (tax_total)
    """
    invoice_id_str = payload.get("id") or payload.get("invoice_id")
    if not invoice_id_str:
        raise ValueError("sales.invoice_posted payload missing 'id' or 'invoice_id'")

    invoice_id = UUID(str(invoice_id_str))
    invoice_number = str(payload.get("invoice_number", f"INV-{invoice_id_str[:8]}"))
    reference = f"INV-{invoice_number}"

    existing_entry = await _is_already_journaled(session, reference_id=invoice_id, reference=reference)
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for invoice '%s' (entry_id=%s). Skipping.",
            invoice_number,
            existing_entry.id,
        )
        return existing_entry

    ar_id = await get_default_account_id(session, AccountMappingKey.ACCOUNTS_RECEIVABLE)
    revenue_id = await get_default_account_id(session, AccountMappingKey.SALES_REVENUE)
    tax_id = await get_default_account_id(session, AccountMappingKey.SALES_TAX_PAYABLE)

    grand_total = abs(Decimal(str(payload.get("grand_total", "0"))))
    subtotal = abs(Decimal(str(payload.get("subtotal", "0"))))
    tax_total = abs(Decimal(str(payload.get("tax_total", "0"))))

    lines = []
    if grand_total > Decimal("0"):
        lines.append({
            "account_id": ar_id,
            "debit": grand_total,
            "credit": Decimal("0.0000"),
            "description": f"Accounts Receivable — Invoice {invoice_number}",
        })

    if subtotal > Decimal("0"):
        lines.append({
            "account_id": revenue_id,
            "debit": Decimal("0.0000"),
            "credit": subtotal,
            "description": f"Sales Revenue — Invoice {invoice_number}",
        })

    if tax_total > Decimal("0"):
        lines.append({
            "account_id": tax_id,
            "debit": Decimal("0.0000"),
            "credit": tax_total,
            "description": f"Sales Tax — Invoice {invoice_number}",
        })

    entry = await create_journal_entry(
        session=session,
        description=f"Sales Invoice {invoice_number}",
        entry_date=None,
        lines=lines,
        reference_id=invoice_id,
        reference=reference,
        source_type="sales.invoice",
        source_id=invoice_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for sales.invoice_posted (%s) | DR AR=%s, CR Rev=%s, CR Tax=%s",
        entry.id,
        invoice_number,
        grand_total,
        subtotal,
        tax_total,
    )
    return entry


@event_bus.subscribe("sales.invoice_posted")
async def handle_invoice_posted(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for sales.invoice_posted."""
    if session is not None:
        return await process_invoice_posted(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_invoice_posted(sess, event.payload, str(event.event_id))


# ── 2. sales.credit_note_posted ───────────────────────────────────────────────


async def process_credit_note_posted(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> JournalEntry | None:
    """
    Process sales.credit_note_posted event and generate a balanced JournalEntry:
      CR  Accounts Receivable   (grand_total)
      DR  Sales Revenue         (subtotal)
      DR  Sales Tax Payable     (tax_total)
    """
    source_id_str = (
        payload.get("credit_note_id")
        or payload.get("id")
        or payload.get("return_id")
    )
    if not source_id_str:
        raise ValueError("sales.credit_note_posted payload missing source 'id'")

    source_id = UUID(str(source_id_str))
    return_number = str(payload.get("return_number", f"RET-{source_id_str[:8]}"))
    reference = f"CN-{return_number}"

    existing_entry = await _is_already_journaled(session, reference_id=source_id, reference=reference)
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for Credit Note '%s' (entry_id=%s). Skipping.",
            reference,
            existing_entry.id,
        )
        return existing_entry

    ar_id = await get_default_account_id(session, AccountMappingKey.ACCOUNTS_RECEIVABLE)
    revenue_id = await get_default_account_id(session, AccountMappingKey.SALES_REVENUE)
    tax_id = await get_default_account_id(session, AccountMappingKey.SALES_TAX_PAYABLE)

    grand_total = abs(Decimal(str(payload.get("grand_total", "0"))))
    subtotal = abs(Decimal(str(payload.get("subtotal", "0"))))
    tax_total = abs(Decimal(str(payload.get("tax_total", "0"))))

    lines = []
    if grand_total > Decimal("0"):
        lines.append({
            "account_id": ar_id,
            "debit": Decimal("0.0000"),
            "credit": grand_total,
            "description": f"Accounts Receivable Reversal — {reference}",
        })

    if subtotal > Decimal("0"):
        lines.append({
            "account_id": revenue_id,
            "debit": subtotal,
            "credit": Decimal("0.0000"),
            "description": f"Sales Revenue Reversal — {reference}",
        })

    if tax_total > Decimal("0"):
        lines.append({
            "account_id": tax_id,
            "debit": tax_total,
            "credit": Decimal("0.0000"),
            "description": f"Sales Tax Reversal — {reference}",
        })

    entry = await create_journal_entry(
        session=session,
        description=f"Sales Credit Note {reference}",
        entry_date=None,
        lines=lines,
        reference_id=source_id,
        reference=reference,
        source_type="sales.credit_note",
        source_id=source_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for sales.credit_note_posted (%s) | CR AR=%s, DR Rev=%s, DR Tax=%s",
        entry.id,
        reference,
        grand_total,
        subtotal,
        tax_total,
    )
    return entry


@event_bus.subscribe("sales.credit_note_posted")
async def handle_credit_note_posted(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for sales.credit_note_posted."""
    if session is not None:
        return await process_credit_note_posted(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_credit_note_posted(sess, event.payload, str(event.event_id))


# ── 3. inventory.stock_take_posted ────────────────────────────────────────────


async def process_stock_take_posted(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> JournalEntry | None:
    """
    Process inventory.stock_take_posted event and generate a balanced JournalEntry:
      If Gain: DR Inventory Asset, CR Stock Variance Expense.
      If Loss (Shrinkage): DR Stock Variance Expense, CR Inventory Asset.
    """
    stock_take_id_str = payload.get("stock_take_id") or payload.get("id")
    if not stock_take_id_str:
        raise ValueError("inventory.stock_take_posted payload missing 'stock_take_id'")

    stock_take_id = UUID(str(stock_take_id_str))
    reference = str(payload.get("reference_id", f"ST-{stock_take_id_str[:8]}"))

    existing_entry = await _is_already_journaled(session, reference_id=stock_take_id, reference=reference)
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for StockTake '%s' (entry_id=%s). Skipping.",
            reference,
            existing_entry.id,
        )
        return existing_entry

    inv_asset_id = await get_default_account_id(session, AccountMappingKey.INVENTORY_ASSET)
    variance_id = await get_default_account_id(session, AccountMappingKey.STOCK_VARIANCE_EXPENSE)

    # Prioritize monetary values (_value), falling back to unit quantities (_qty) if values are omitted
    gain_value = abs(Decimal(str(payload.get("total_gain_value", payload.get("total_gain_qty", "0")))))
    loss_value = abs(Decimal(str(payload.get("total_loss_value", payload.get("total_loss_qty", "0")))))

    if gain_value == Decimal("0") and loss_value == Decimal("0"):
        logger.info(
            "StockTake '%s' has zero financial variance (gain=%s, loss=%s). Skipping journal entry.",
            reference,
            gain_value,
            loss_value,
        )
        return None

    lines = []
    if gain_value > Decimal("0"):
        lines.append({
            "account_id": inv_asset_id,
            "debit": gain_value,
            "credit": Decimal("0.0000"),
            "description": f"Inventory Gain — StockTake {reference}",
        })
        lines.append({
            "account_id": variance_id,
            "debit": Decimal("0.0000"),
            "credit": gain_value,
            "description": f"Stock Variance Gain — StockTake {reference}",
        })

    if loss_value > Decimal("0"):
        lines.append({
            "account_id": variance_id,
            "debit": loss_value,
            "credit": Decimal("0.0000"),
            "description": f"Stock Variance Loss (Shrinkage) — StockTake {reference}",
        })
        lines.append({
            "account_id": inv_asset_id,
            "debit": Decimal("0.0000"),
            "credit": loss_value,
            "description": f"Inventory Shrinkage — StockTake {reference}",
        })

    entry = await create_journal_entry(
        session=session,
        description=f"Stock Take Variance {reference}",
        entry_date=None,
        lines=lines,
        reference_id=stock_take_id,
        reference=reference,
        source_type="inventory.stock_take",
        source_id=stock_take_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for inventory.stock_take_posted (%s) | Gain=%s, Loss=%s",
        entry.id,
        reference,
        gain_value,
        loss_value,
    )
    return entry


# ── 4. sales.payment_received ─────────────────────────────────────────────────


async def process_payment_received(
    session: AsyncSession,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> JournalEntry | None:
    """
    Process sales.payment_received event (Wave 3 item 1 — customer payments)
    and generate a balanced JournalEntry clearing the receivable:
      DR  Cash / Bank Account   (amount)   ← Asset increases
      CR  Accounts Receivable   (amount)   ← Receivable cleared
    """
    payment_id_str = payload.get("payment_id") or payload.get("id")
    if not payment_id_str:
        raise ValueError("sales.payment_received payload missing 'payment_id' or 'id'")

    payment_id = UUID(str(payment_id_str))
    payment_number = str(payload.get("payment_number", f"PAY-{payment_id_str[:8]}"))
    reference = f"RCPT-{payment_number}"

    existing_entry = await _is_already_journaled(session, reference_id=payment_id, reference=reference)
    if existing_entry is not None:
        logger.info(
            "Idempotency check: JournalEntry already exists for customer payment '%s' (entry_id=%s). Skipping.",
            payment_number,
            existing_entry.id,
        )
        return existing_entry

    amount = abs(Decimal(str(payload.get("amount", "0"))))
    if amount <= Decimal("0"):
        logger.warning("Customer payment '%s' has zero amount; skipping journal creation.", payment_number)
        return None

    # Prefer the payment's own treasury_id (a real tenant.accounts.id) when
    # given; otherwise fall back to the tenant's default Cash & Banks
    # mapping — same fallback pattern purchase.payment_made uses.
    from app.modules.accounting.models.core import Account

    cash_id = None
    treasury_id_str = payload.get("treasury_id")
    if treasury_id_str:
        try:
            acct_res = await session.execute(select(Account).where(Account.id == UUID(str(treasury_id_str))))
            acct = acct_res.scalar_one_or_none()
            if acct:
                cash_id = acct.id
        except (ValueError, Exception):
            cash_id = None
    if cash_id is None:
        cash_id = await get_default_account_id(session, AccountMappingKey.CASH_AND_BANKS)

    ar_id = await get_default_account_id(session, AccountMappingKey.ACCOUNTS_RECEIVABLE)

    lines = [
        {
            "account_id": cash_id,
            "debit": amount,
            "credit": Decimal("0.0000"),
            "description": f"Cash/Bank received — {payment_number}",
        },
        {
            "account_id": ar_id,
            "debit": Decimal("0.0000"),
            "credit": amount,
            "description": f"Accounts Receivable cleared — {payment_number}",
        },
    ]

    entry = await create_journal_entry(
        session=session,
        description=f"Customer Payment {payment_number}",
        entry_date=None,
        lines=lines,
        reference_id=payment_id,
        reference=reference,
        source_type="sales.payment",
        source_id=payment_id,
        status=JournalEntryStatus.POSTED,
    )
    logger.info(
        "✅ Generated GL JournalEntry id=%s for sales.payment_received (%s) | DR Cash=%s, CR AR=%s",
        entry.id,
        payment_number,
        amount,
        amount,
    )
    return entry


@event_bus.subscribe("sales.payment_received")
async def handle_payment_received_sales(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for sales.payment_received (customer payments)."""
    if session is not None:
        return await process_payment_received(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_payment_received(sess, event.payload, str(event.event_id))


@event_bus.subscribe("inventory.stock_take_posted")
async def handle_stock_take_posted(
    event: DomainEvent,
    session: AsyncSession | None = None,
) -> JournalEntry | None:
    """EventBus subscriber for inventory.stock_take_posted."""
    if session is not None:
        return await process_stock_take_posted(session, event.payload, str(event.event_id))

    async with tenant_session(event.tenant_id) as sess:
        return await process_stock_take_posted(sess, event.payload, str(event.event_id))
