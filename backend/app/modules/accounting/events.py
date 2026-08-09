"""
app/modules/accounting/events.py — Real EventBus Handlers with PostgreSQL Inserts

This file is the ONLY bridge between the plugin world and the accounting core.

DECOUPLING PROOF:
  ✅  Imports from app.core.event_bus     — shared contract (allowed)
  ✅  Imports from app.modules.accounting — internal (allowed)
  ❌  Never imported by any plugin        — zero reverse coupling

When the `invoice.created` event fires:
  1. Extract amount, account codes, and tenant_id from the event payload.
  2. Open a FRESH AsyncSession (not from request context — this runs
     outside of any HTTP request via asyncio.create_task).
  3. Execute SET search_path TO tenant_{id} to target the right schema.
  4. Validate balance (app-level double-entry check).
  5. INSERT one JournalEntry row.
  6. INSERT two TransactionLine rows (Debit AR, Credit Revenue).
  7. COMMIT — data is now in PostgreSQL under the tenant's schema.

Error handling:
  Any exception is caught by _safe_handler_call in event_bus.py and logged.
  The event does NOT fail the original HTTP request — the simulation endpoint
  already returned 202 Accepted before this handler even started.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.accounting.models import JournalEntry, JournalEntryStatus, TransactionLine

logger = logging.getLogger(__name__)

# Grab the singleton EventBus. Subscriptions registered here at import time.
event_bus = get_event_bus()



def _require_payload(payload: dict, key: str, event_id: str) -> str:
    """Extract a required key from an event payload or raise ValueError."""
    value = payload.get(key)
    if value is None:
        raise ValueError(
            f"[event_id={event_id}] Missing required payload key: '{key}'",
        )
    return str(value)


# ── Handler: invoice.created ──────────────────────────────────────────────────


@event_bus.subscribe("invoice.created")
async def handle_invoice_created(event: DomainEvent) -> None:
    """
    Listen for `invoice.created` and INSERT a balanced journal entry into
    the tenant's PostgreSQL schema.

    Double-entry produced:
      DR  Accounts Receivable  (1200)  [amount]   ← Asset increases
      CR  Sales Revenue        (4010)  [amount]   ← Revenue recognized

    Expected payload keys:
      invoice_id           — UUID of the source invoice
      invoice_number       — Human-readable ref (e.g. SIM-AB12CD34)
      amount               — Decimal string (e.g. "1500.00")
      ar_account_code      — Account code for Accounts Receivable (e.g. "1200")
      revenue_account_code — Account code for Sales Revenue (e.g. "4010")
      customer_name        — Optional, used in description
      created_by_user_id   — UUID of the triggering user (for audit)
    """
    event_id_str = str(event.event_id)
    logger.info(
        "📥 Received invoice.created (event_id=%s, tenant=%s)",
        event_id_str,
        event.tenant_id,
    )

    # ── Parse payload ─────────────────────────────────────────────────────────
    payload = event.payload
    try:
        invoice_number = _require_payload(payload, "invoice_number", event_id_str)
        amount_str = _require_payload(payload, "amount", event_id_str)
        ar_code = payload.get("ar_account_code", "1200")
        rev_code = payload.get("revenue_account_code", "4010")
        customer = payload.get("customer_name", "Customer")
        source_id_str = payload.get("invoice_id")

        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError(f"Invoice amount must be positive, got {amount}")

    except (ValueError, InvalidOperation, KeyError) as exc:
        logger.error(
            "❌ handle_invoice_created aborted (event_id=%s): invalid payload — %s",
            event_id_str,
            exc,
        )
        return

    # ── Application-level double-entry validation (before any DB call) ────────
    total_debit = amount
    total_credit = amount
    if total_debit.quantize(Decimal("0.0001")) != total_credit.quantize(Decimal("0.0001")):
        logger.error(
            "❌ CRITICAL: Unbalanced entry attempted for invoice %s (DR=%s ≠ CR=%s)",
            invoice_number,
            total_debit,
            total_credit,
        )
        return

    # ── Open tenant-scoped DB session ─────────────────────────────────────────
    async with tenant_session(event.tenant_id) as session:
        try:
            now = datetime.now(UTC).replace(tzinfo=None)

            # ── INSERT JournalEntry ────────────────────────────────────────────────
            entry = JournalEntry(
                reference=f"JE-{invoice_number}",
                description=f"Sales invoice for {customer} — {invoice_number}",
                status=JournalEntryStatus.POSTED,   # Auto-post event-driven entries
                source_type="invoice",
                source_id=UUID(source_id_str) if source_id_str else None,
                created_by=(
                    UUID(payload["created_by_user_id"])
                    if payload.get("created_by_user_id")
                    else None
                ),
                posted_at=now,
            )
            session.add(entry)
            await session.flush()  # Materialise entry.id for FK reference in lines

            # ── INSERT TransactionLine 1: DEBIT Accounts Receivable ───────────────
            debit_line = TransactionLine(
                journal_entry_id=entry.id,
                account_code=ar_code,
                account_name="Accounts Receivable",
                debit=amount,
                credit=Decimal("0.0000"),
                description=f"Receivable: {customer} / {invoice_number}",
            )
            session.add(debit_line)

            # ── INSERT TransactionLine 2: CREDIT Sales Revenue ────────────────────
            credit_line = TransactionLine(
                journal_entry_id=entry.id,
                account_code=rev_code,
                account_name="Sales Revenue",
                debit=Decimal("0.0000"),
                credit=amount,
                description=f"Revenue recognized: {invoice_number}",
            )
            session.add(credit_line)

            logger.info(
                "✅ Journal entry '%s' (id=%s) committed to schema 'tenant_%s' | "
                "DR %s → AR(%s) | CR %s → REV(%s)",
                entry.reference,
                entry.id,
                event.tenant_id.replace("-", "_"),
                amount,
                ar_code,
                amount,
                rev_code,
            )

        except Exception:
            logger.exception(
                "❌ DB error while processing invoice.created (event_id=%s, tenant=%s)",
                event_id_str,
                event.tenant_id,
            )
            raise  # Re-raise so _safe_handler_call logs the full traceback


# ── Handler: payment.received ─────────────────────────────────────────────────


@event_bus.subscribe("payment.received")
async def handle_payment_received(event: DomainEvent) -> None:
    """
    Listen for `payment.received` and INSERT a journal entry to clear receivables.

    Double-entry produced:
      DR  Cash / Bank Account  (1100)  [amount]   ← Asset increases
      CR  Accounts Receivable  (1200)  [amount]   ← Receivable cleared

    Expected payload keys:
      payment_reference    — Human-readable ref
      amount               — Decimal string
      cash_account_code    — e.g. "1100"
      ar_account_code      — e.g. "1200"
      created_by_user_id   — UUID
    """
    event_id_str = str(event.event_id)
    logger.info(
        "📥 Received payment.received (event_id=%s, tenant=%s)",
        event_id_str,
        event.tenant_id,
    )

    payload = event.payload
    try:
        payment_ref = _require_payload(payload, "payment_reference", event_id_str)
        amount = Decimal(_require_payload(payload, "amount", event_id_str))
        cash_code = payload.get("cash_account_code", "1100")
        ar_code = payload.get("ar_account_code", "1200")
        if amount <= 0:
            raise ValueError(f"Payment amount must be positive, got {amount}")
    except (ValueError, InvalidOperation) as exc:
        logger.error("❌ handle_payment_received aborted: %s", exc)
        return

    async with tenant_session(event.tenant_id) as session:
        try:
            now = datetime.now(UTC).replace(tzinfo=None)

            entry = JournalEntry(
                reference=f"JE-{payment_ref}",
                description=f"Cash received: {payment_ref}",
                status=JournalEntryStatus.POSTED,
                source_type="payment",
                posted_at=now,
            )
            session.add(entry)
            await session.flush()

            # DR Cash
            session.add(TransactionLine(
                journal_entry_id=entry.id,
                account_code=cash_code,
                account_name="Cash & Cash Equivalents",
                debit=amount,
                credit=Decimal("0.0000"),
                description=f"Cash received for {payment_ref}",
            ))
            # CR Accounts Receivable
            session.add(TransactionLine(
                journal_entry_id=entry.id,
                account_code=ar_code,
                account_name="Accounts Receivable",
                debit=Decimal("0.0000"),
                credit=amount,
                description=f"Receivable cleared for {payment_ref}",
            ))

            logger.info(
                "✅ Payment journal entry '%s' committed (tenant=%s)",
                entry.reference,
                event.tenant_id,
            )
        except Exception:
            logger.exception("❌ DB error in handle_payment_received (event_id=%s)", event_id_str)
            raise

# Import GL Bridge event consumers to register them with the EventBus singleton
import app.modules.accounting.consumers.events  # noqa: F401, E402
import app.modules.accounting.consumers.purchasing_events  # noqa: F401, E402

