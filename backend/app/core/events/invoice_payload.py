"""
app/core/events/invoice_payload.py — The `invoice.created` payload contract

WHY THIS EXISTS (live-confirmed P0, 14 Sep 2026)
------------------------------------------------
`app/modules/accounting/events.py::handle_invoice_created` is the ONLY
subscriber of "invoice.created" and the only thing in the codebase that turns a
vertical plugin's revenue event into a real double-entry JournalEntry. It needs
a small set of keys — and until now each of the four vertical plugins built that
dict by hand, inline, with no shared definition of what "valid" meant:

  * hospitality → included invoice_number ✅
  * rental      → included invoice_number ✅
  * recruitment → included invoice_number ✅
  * travel      → DID NOT (app/plugins/travel/listeners.py) ❌

Because the handler answered a missing key with `logger.error(...)` + `return`,
a travel booking could be confirmed (HTTP 200, `gl_receivable_posted: true`
stamped on the Case) while zero journal entries existed in the ledger. Silent,
invisible, and only discoverable by reading the GL afterwards.

Two defences live here:

  1. `build_invoice_created_payload()` — the ONE place a plugin builds this
     payload. It cannot produce a dict that is missing a required key, because
     each one is a mandatory keyword argument that is validated before return.
  2. `assert_invoice_payload_contract()` — called by the accounting handler on
     the receiving end, so a hand-rolled payload from anywhere else (an old call
     site, a new plugin, a replayed outbox row) fails LOUDLY with a dedicated
     exception type instead of being dropped.

Note on why raising is the right call even though EventBus swallows it:
app/core/events/event_bus.py deliberately catches every handler exception so one
broken subscriber cannot abort an unrelated publisher's transaction. It logs the
swallowed exception with `logger.exception(...)`, i.e. a full traceback naming
this module's exception class — which is exactly the loud, greppable signal that
was missing when the failure mode was a single `logger.error` line.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

# Keys handle_invoice_created() cannot work without. `amount` must also be a
# positive number — a zero/negative amount is rejected by the handler too.
REQUIRED_KEYS: tuple[str, ...] = (
    "invoice_number",
    "amount",
    "ar_account_code",
    "revenue_account_code",
    # Identity of the business event. Without these three, the gl_postings
    # UNIQUE (source_type, source_id, entry_kind) cannot guarantee exactly-once
    # posting, so handle_invoice_created refuses the payload rather than posting
    # something it can never de-duplicate. See app/modules/accounting/
    # models/posting.py for the list of entry kinds in use.
    "source_type",
    "source_id",
    "entry_type",
)


class InvoicePayloadContractError(ValueError):
    """An `invoice.created` payload is missing keys the GL handler requires.

    Raised by `assert_invoice_payload_contract()` (receiving end) and by
    `build_invoice_created_payload()` (publishing end).
    """


def assert_invoice_payload_contract(payload: dict[str, Any], *, context: str = "") -> None:
    """Raise InvoicePayloadContractError unless `payload` satisfies the contract.

    `context` is a free-form label (event id, source plugin) folded into the
    message so a swallowed-and-logged failure is traceable back to its emitter.
    """
    missing = [key for key in REQUIRED_KEYS if payload.get(key) is None]
    if missing:
        raise InvoicePayloadContractError(
            f"invoice.created payload is missing required key(s): "
            f"{', '.join(missing)}. Present keys: {sorted(payload)}. "
            f"Every publisher must build this payload with "
            f"app.core.events.invoice_payload.build_invoice_created_payload()."
            + (f" [{context}]" if context else "")
        )


def build_invoice_created_payload(
    *,
    source: str,
    source_id: str,
    entry_type: str,
    invoice_number: str,
    amount: float | Decimal,
    revenue_account_code: str,
    ar_account_code: str,
    source_type: str = "case",
    customer_name: str | None = None,
    description: str | None = None,
    currency: str = "EGP",
    entry_date: str | date | None = None,
    invoice_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a contract-valid `invoice.created` payload.

    Required-by-the-GL-handler fields are mandatory keyword arguments, so a
    plugin physically cannot emit the payload that broke Travel. Anything
    vertical-specific (line_items, nights, margin, case_stage, ...) rides along
    via **extra and is preserved verbatim for the audit trail.

    `receivable_account_code` is emitted alongside `ar_account_code` with the
    same value: the GL handler reads ONLY `ar_account_code`, but other tooling
    and existing payload consumers still read the longer name.
    """
    payload: dict[str, Any] = {
        "source": source,
        "source_type": source_type,
        "source_id": str(source_id),
        # entry_type doubles as gl_postings.entry_kind — it is what allows a
        # legitimate second posting against the same source (a reversal is a
        # different kind) while blocking a repeat of the same one.
        "entry_type": entry_type,
        "invoice_id": str(invoice_id if invoice_id is not None else source_id),
        "invoice_number": invoice_number,
        "customer_name": customer_name or str(source_id),
        "amount": float(amount),
        "currency": currency,
        "revenue_account_code": revenue_account_code,
        "ar_account_code": ar_account_code,
        # Kept for non-GL consumers; handle_invoice_created ignores this one.
        "receivable_account_code": ar_account_code,
        "entry_date": (
            entry_date.isoformat() if isinstance(entry_date, date)
            else (entry_date or date.today().isoformat())
        ),
    }
    if description is not None:
        payload["description"] = description
    payload.update(extra)

    assert_invoice_payload_contract(payload, context=f"source={source} id={source_id}")
    return payload
