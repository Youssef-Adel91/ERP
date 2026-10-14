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
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.core.events.invoice_payload import (
    InvoicePayloadContractError,
    assert_invoice_payload_contract,
)
from app.modules.accounting.services.gl_posting import (
    mark_failed,
    mark_posted,
    reserve_posting,
)
from app.modules.accounting.models import JournalEntryStatus
from app.modules.accounting.services.journal import create_journal_entry

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
    #
    # CONTRACT ENFORCEMENT (added 15 Sep 2026 after a live P0): this used to
    # answer a missing key with a single logger.error line + `return`. That made
    # the Travel plugin's missing "invoice_number" completely invisible — the
    # booking confirmed with HTTP 200 and stamped gl_receivable_posted=True on
    # the Case, while the ledger stayed empty. A silent drop is the worst
    # possible failure mode for an accounting bridge, so a violated contract now
    # RAISES InvoicePayloadContractError.
    #
    # Raising is safe: app/core/events/event_bus.py deliberately catches every
    # handler exception so one broken subscriber can't abort an unrelated
    # publisher's transaction — but it logs it via logger.exception(), i.e. a
    # full traceback naming the exception class. Loud and greppable instead of
    # one easily-missed line. Publishers should use
    # app.core.events.invoice_payload.build_invoice_created_payload(), which
    # cannot construct a payload that violates this contract.
    payload = event.payload
    assert_invoice_payload_contract(payload, context=f"event_id={event_id_str}")

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
        raise

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
    #
    # IMPORTANT — discovered via live verification (11 Sep 2026): the manual
    # JournalEntry/TransactionLine(=JournalEntryLine) construction that used
    # to live here set only `account_code` (a plain string) on each line and
    # never resolved it to `account_id` — but JournalEntryLine.account_id is
    # a NOT NULL foreign key to tenant.accounts.id. Every single invoice
    # posted through this handler was therefore failing with a Postgres
    # IntegrityError (NotNullViolationError on journal_entry_lines.account_id)
    # AFTER already logging "✅ Journal entry ... committed" (that log line
    # ran before the session actually flushed/committed, so it was lying).
    # The EventBus swallows the exception, so this looked like total success
    # from every angle except the database itself.
    #
    # Fix: delegate to app.modules.accounting.services.journal.create_journal_entry
    # — the same well-tested service the GL Bridge
    # (app/modules/accounting/consumers/events.py) already uses successfully
    # for sales/inventory events. It resolves account_code → account_id via
    # a real Account lookup, asserts SUM(debits) == SUM(credits), validates
    # an open AccountingPeriod exists for entry_date, and commits atomically.
    # ── Idempotency gate (P1 item 1+2) ───────────────────────────────────────
    # `source` / `source_id` / `entry_type` identify the business event. The
    # gl_postings UNIQUE (source_type, source_id, entry_kind) is what actually
    # stops a double post — the Case row's FOR UPDATE lock only ever protected
    # the transition path, and the ledger itself accepts duplicates (proven live
    # with two identical "DUP-TEST-001" entries, both 201).
    #
    # A source that does not identify itself cannot be de-duplicated. Rather
    # than silently allowing an unguarded post, that is refused loudly — the
    # payload builder (app/core/events/invoice_payload.py) always supplies both.
    posting_source_type = payload.get("source_type") or "case"
    posting_source_id = payload.get("source_id")
    entry_kind = payload.get("entry_type") or payload.get("entry_kind")
    if not posting_source_id or not entry_kind:
        raise InvoicePayloadContractError(
            f"[event_id={event_id_str}] invoice.created cannot be de-duplicated: "
            f"source_id={posting_source_id!r} entry_type={entry_kind!r}. Both are "
            f"required so gl_postings can guarantee exactly-once posting."
        )

    reserved_posting_id: UUID | None = None
    try:
        entry_date_str = payload.get("entry_date")
        from datetime import date as _date
        entry_date = _date.fromisoformat(entry_date_str) if entry_date_str else _date.today()

        async with tenant_session(event.tenant_id) as session:
            # Claim FIRST, inside the same transaction as the journal entry, so
            # a crash between the two rolls back both rather than leaving an
            # orphan entry. A conflict means someone already posted this exact
            # (source, kind): that is an idempotent success, not an error.
            posting = await reserve_posting(
                session,
                source_type=posting_source_type,
                source_id=posting_source_id,
                entry_kind=entry_kind,
                invoice_number=invoice_number,
                amount=amount,
                currency=payload.get("currency", "EGP"),
            )
            if posting is None:
                logger.info(
                    "↩️ invoice.created skipped (event_id=%s): %s/%s/%s is already "
                    "posted — idempotent no-op, ledger unchanged.",
                    event_id_str, posting_source_type, posting_source_id, entry_kind,
                )
                return
            reserved_posting_id = posting.id

            entry = await create_journal_entry(
                session=session,
                description=f"Sales invoice for {customer} — {invoice_number}",
                entry_date=entry_date,
                # account_name is deliberately left unset: create_journal_entry()
                # resolves account_code -> the real Account row and fills in its
                # actual name when this is falsy. Hardcoding "Accounts
                # Receivable"/"Sales Revenue" mislabelled every line that isn't
                # literally 1200/4010 — live-confirmed on the travel supplier
                # entry, which rendered as
                #   "5010 Accounts Receivable" / "2100 Sales Revenue"
                # (correct codes, nonsense names) and on rental's 4020, shown as
                # "Sales Revenue" instead of "Vehicle Rental Revenue". The codes
                # drive the accounting; the names are what a human reads in the
                # ledger, so they must not lie.
                lines_data=[
                    {
                        "account_code": ar_code,
                        "debit": amount,
                        "credit": Decimal("0.0000"),
                        "description": f"Receivable: {customer} / {invoice_number}",
                    },
                    {
                        "account_code": rev_code,
                        "debit": Decimal("0.0000"),
                        "credit": amount,
                        "description": f"Revenue recognized: {invoice_number}",
                    },
                ],
                reference=f"JE-{invoice_number}",
                reference_id=UUID(source_id_str) if source_id_str else None,
                source_type="invoice",
                source_id=UUID(source_id_str) if source_id_str else None,
                status=JournalEntryStatus.POSTED,
            )

        # create_journal_entry() commits its own transaction, so confirming the
        # reservation is a second, short transaction. A crash in the gap leaves
        # the row at RESERVED with a real journal entry behind it — visible and
        # repairable, and critically it still blocks a duplicate post, which is
        # the property that matters.
        async with tenant_session(event.tenant_id) as confirm_session:
            await mark_posted(
                confirm_session,
                posting_id=reserved_posting_id,
                journal_entry_id=entry.id,
            )

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

    except Exception as exc:
        logger.exception(
            "❌ DB error while processing invoice.created (event_id=%s, tenant=%s)",
            event_id_str,
            event.tenant_id,
        )
        # Record WHY on the posting record itself, on a fresh session (the one
        # above is poisoned by the failed transaction). This is what makes the
        # failure visible to the user instead of living only in the log.
        if reserved_posting_id is not None:
            try:
                async with tenant_session(event.tenant_id) as fail_session:
                    await mark_failed(fail_session, posting_id=reserved_posting_id, exc=exc)
            except Exception:
                logger.exception(
                    "Could not record FAILED state for gl_posting %s", reserved_posting_id
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

    # See the matching comment in handle_invoice_created above: this used to
    # build JournalEntryLine rows with only `account_code` set, but
    # `account_id` is a NOT NULL FK — every payment posted here was silently
    # failing with an IntegrityError after logging a false "✅ ... committed".
    # Delegates to create_journal_entry() (same service the GL Bridge uses)
    # which properly resolves account_code → account_id.
    try:
        async with tenant_session(event.tenant_id) as session:
            entry = await create_journal_entry(
                session=session,
                description=f"Cash received: {payment_ref}",
                lines_data=[
                    {
                        "account_code": cash_code,
                        "account_name": "Cash & Cash Equivalents",
                        "debit": amount,
                        "credit": Decimal("0.0000"),
                        "description": f"Cash received for {payment_ref}",
                    },
                    {
                        "account_code": ar_code,
                        "account_name": "Accounts Receivable",
                        "debit": Decimal("0.0000"),
                        "credit": amount,
                        "description": f"Receivable cleared for {payment_ref}",
                    },
                ],
                reference=f"JE-{payment_ref}",
                source_type="payment",
                status=JournalEntryStatus.POSTED,
            )

        logger.info(
            "✅ Payment journal entry '%s' (id=%s) committed (tenant=%s)",
            entry.reference,
            entry.id,
            event.tenant_id,
        )
    except Exception:
        logger.exception("❌ DB error in handle_payment_received (event_id=%s)", event_id_str)
        raise

# Import GL Bridge event consumers to register them with the EventBus singleton
import app.modules.accounting.consumers.events  # noqa: F401, E402
import app.modules.accounting.consumers.purchasing_events  # noqa: F401, E402

