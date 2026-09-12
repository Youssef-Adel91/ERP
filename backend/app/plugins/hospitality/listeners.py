"""
app/plugins/hospitality/listeners.py — Hospitality Financial Event Hooks

Subscribes to CaseStageTransitionedEvent (plugin_key = "hospitality").

checked_out →  calls calculate_folio_total() and posts the consolidated
               hotel revenue to the GL via InvoiceCreatedEvent.
               Idempotent: guarded by Case.data["gl_revenue_posted"].

cancelled   →  posts any cancellation penalty as earned revenue.

DECOUPLING CONTRACT:
  ✅ Subscribes via EventBus — zero coupling to trigger
  ✅ Reads GL account codes from CaseType.meta
  ✅ Posts GL entries by publishing InvoiceCreatedEvent
  ❌ Never imports from app.modules.accounting
  ❌ Never writes JournalEntry rows directly
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, InvoiceCreatedEvent, get_event_bus
from app.modules.cases.models.core import Case, CaseType
from app.plugins.hospitality.services.folio import calculate_folio_total

logger = logging.getLogger(__name__)
event_bus = get_event_bus()

_CHECKOUT_STAGE = "checked_out"
_CANCEL_STAGE = "cancelled"


async def _post_checkout_revenue(
    session,
    case: Case,
    ct: CaseType,
    tenant_id: str,
) -> None:
    """
    Posts the consolidated folio at checkout:
      DR Accounts Receivable (1200)
      CR Hotel Revenue        (4010)

    The folio total includes: room charge, board supplement, extras, tax, and service charge.
    Deposits are subtracted to produce the balance due, which is what gets posted.
    """
    if case.data.get("gl_revenue_posted"):
        logger.info("Hospitality GL: already posted for case %s — skipping", case.id)
        return

    meta = ct.meta or {}
    folio = await calculate_folio_total(
        session=session,
        case_id=case.id,
        case_data=case.data,
        case_start=case.start_date,
        case_end=case.end_date,
        meta=meta,
    )

    if folio.total <= 0:
        logger.info("Hospitality GL: zero folio total for case %s — skipping", case.id)
        return

    revenue_account = meta.get("revenue_gl_account", "4010")
    receivable_account = meta.get("receivable_gl_account", "1200")

    # Build a compact line-item summary for the GL journal narration
    line_summary = [
        {"description": line.description, "amount": float(line.amount)}
        for line in folio.lines
    ]

    # NOTE: app/modules/accounting/events.py's handle_invoice_created() —
    # the ONLY subscriber of "invoice.created" — requires "invoice_number"
    # and "amount" in the payload (silently aborts with a logged error,
    # never raises, if either is missing) and reads the AR account code
    # from "ar_account_code" (receivable_account_code is kept for other
    # tooling but the handler itself ignores it). Discovered via live
    # verification: case.data["gl_revenue_posted"] was set to True by this
    # listener even though the downstream JournalEntry was silently never
    # created — the flag only reflects that WE published the event, not
    # that accounting successfully processed it.
    invoice_number = f"HOSP-{case.id.hex[:8].upper()}-CO"
    customer_name = case.data.get("guest_name_ar") or case.data.get("guest_name") or str(case.id)
    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "source": "hospitality_plugin",
                "source_id": str(case.id),
                "invoice_id": str(case.id),
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "entry_type": "hotel_checkout_revenue",
                "description": (
                    f"Hotel Checkout — {customer_name}"
                    f" · {folio.nights} ليلة · {folio.check_in} → {folio.check_out}"
                ),
                "amount": float(folio.total),
                "balance_due": float(folio.balance_due),
                "currency": folio.currency,
                "revenue_account_code": revenue_account,
                "receivable_account_code": receivable_account,
                "ar_account_code": receivable_account,
                "entry_date": folio.check_out,
                # Breakdown for audit trail
                "room_charge": float(folio.room_charge),
                "board_charge": float(folio.board_charge),
                "extras_total": float(folio.extras_total),
                "service_charge": float(folio.service_charge),
                "tax_amount": float(folio.tax_amount),
                "deposit_offset": float(folio.deposit_total),
                "nights": folio.nights,
                "line_items": line_summary,
            },
        ),
        session=session,
    )

    # Stamp the idempotency flag and persist the folio total on the case
    case.data = {
        **case.data,
        "gl_revenue_posted": True,
        "folio_total": float(folio.total),
        "final_folio_total": float(folio.total),
    }
    session.add(case)


async def _post_cancellation_penalty(
    session,
    case: Case,
    ct: CaseType,
    tenant_id: str,
) -> None:
    """Posts cancellation penalty as earned revenue (if not already posted)."""
    if case.data.get("gl_refund_posted"):
        return

    from decimal import Decimal
    penalty = Decimal(str(case.data.get("cancellation_penalty", "0") or "0"))
    if penalty <= 0:
        case.data = {**case.data, "gl_refund_posted": True}
        session.add(case)
        return

    meta = ct.meta or {}
    receivable_account = meta.get("receivable_gl_account", "1200")
    customer_name = case.data.get("guest_name_ar") or case.data.get("guest_name") or str(case.id)
    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "source": "hospitality_plugin",
                "source_id": str(case.id),
                "invoice_id": str(case.id),
                "invoice_number": f"HOSP-{case.id.hex[:8].upper()}-CANC",
                "customer_name": customer_name,
                "entry_type": "cancellation_penalty",
                "description": f"Hotel Cancellation Penalty — {customer_name}",
                "amount": float(penalty),
                "currency": case.data.get("currency", "EGP"),
                "revenue_account_code": meta.get("revenue_gl_account", "4010"),
                "receivable_account_code": receivable_account,
                "ar_account_code": receivable_account,
                "entry_date": __import__("datetime").date.today().isoformat(),
                "case_stage": _CANCEL_STAGE,
            },
        ),
        session=session,
    )

    case.data = {**case.data, "gl_refund_posted": True}
    session.add(case)


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _mark_posting_failed(tenant_id: str, case_id_str: str, to_stage: str, exc: Exception) -> None:
    """Best-effort, separate-connection write of the posting_failed flag —
    used whenever we can't trust the session that just raised (it may be in
    a broken state) or don't have one at all."""
    try:
        async with tenant_session(tenant_id) as fail_session:
            failed_case = await fail_session.get(Case, uuid.UUID(case_id_str))
            if failed_case:
                failed_case.data = {
                    **failed_case.data,
                    "posting_failed": True,
                    "posting_error": f"{type(exc).__name__}: {exc}"[:500],
                    "posting_failed_stage": to_stage,
                }
                fail_session.add(failed_case)
    except Exception:
        logger.exception(
            "Hospitality listener: failed to record posting_failed flag for case %s",
            case_id_str,
        )


# ── EventBus Handler ───────────────────────────────────────────────────────────


@event_bus.subscribe("case.stage.transitioned")
async def handle_hospitality_stage_transitioned(event: DomainEvent, session: AsyncSession | None = None) -> None:
    """
    Reacts to Case transitions ONLY for the hospitality plugin.
    All other plugins' events pass through without effect.

    `session`: EventBus.publish() passes its caller's own session automatically
    whenever this handler's signature accepts a `session` kwarg. We MUST prefer
    that session over opening a fresh tenant_session() when one is available:
    the Case Engine's transition_case() only *flushes* the case's data changes
    (e.g. folio-relevant fields set in the very same API call that moves the
    case to "checked_out") — the caller commits afterwards. A brand-new
    tenant_session() opens a separate DB connection/transaction, and under
    Postgres's default READ COMMITTED isolation it would NOT see those
    flushed-but-uncommitted changes. See recruitment/listeners.py for the
    reference implementation of this pattern.
    """
    payload = event.payload

    if payload.get("plugin_key") != "hospitality":
        return

    to_stage = payload.get("to_stage")
    if to_stage not in (_CHECKOUT_STAGE, _CANCEL_STAGE):
        return

    case_id_str = payload.get("case_id")
    if not case_id_str:
        return

    tenant_id = event.tenant_id
    if not tenant_id:
        logger.warning(
            "Hospitality listener: event for case %s carries no tenant_id — cannot "
            "resolve tenant schema, skipping financial posting.", case_id_str,
        )
        return

    if session is not None:
        # Fast path — reuse the caller's already tenant-scoped session so we
        # can see flushed-but-uncommitted changes from the same request.
        try:
            case = await session.get(Case, uuid.UUID(case_id_str))
            if not case:
                logger.warning("Hospitality listener: Case %s not found", case_id_str)
                return
            ct = await session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Hospitality listener: CaseType not found for case %s", case_id_str)
                return

            if to_stage == _CHECKOUT_STAGE:
                await _post_checkout_revenue(session, case, ct, tenant_id)
            elif to_stage == _CANCEL_STAGE:
                await _post_cancellation_penalty(session, case, ct, tenant_id)

            logger.info(
                "Hospitality financial hook completed: case %s → %s (shared-session path)",
                case_id_str, to_stage,
            )
            # No manual commit/rollback — the caller owns this session's
            # transaction boundary.
        except Exception as exc:
            logger.exception(
                "Hospitality listener failed for case %s stage %s (shared-session "
                "path) — marking posting_failed on the case for visibility.",
                case_id_str, to_stage,
            )
            await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
        return

    # Fallback path — no session was supplied (e.g. a future outbox-worker
    # driven dispatch, rather than the synchronous in-process EventBus path).
    try:
        async with tenant_session(tenant_id) as fresh_session:
            case = await fresh_session.get(Case, uuid.UUID(case_id_str))
            if not case:
                logger.warning("Hospitality listener: Case %s not found", case_id_str)
                return

            ct = await fresh_session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Hospitality listener: CaseType not found for case %s", case_id_str)
                return

            if to_stage == _CHECKOUT_STAGE:
                await _post_checkout_revenue(fresh_session, case, ct, tenant_id)
            elif to_stage == _CANCEL_STAGE:
                await _post_cancellation_penalty(fresh_session, case, ct, tenant_id)

        logger.info(
            "Hospitality financial hook completed: case %s → %s", case_id_str, to_stage
        )

    except Exception as exc:
        logger.exception(
            "Hospitality listener failed for case %s stage %s", case_id_str, to_stage
        )
        await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
