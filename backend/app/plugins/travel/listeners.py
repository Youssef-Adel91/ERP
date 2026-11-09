"""
app/plugins/travel/listeners.py — Travel Plugin Financial Event Hooks

Subscribes to CaseStageTransitionedEvent from the Core Case Engine.
Triggers GL postings at key lifecycle moments:

  Stage: confirmed →  DR Accounts Receivable (customer owes sell_price)
                      CR Accounts Payable    (agency owes supplier buy_price)
                      CR Revenue             (agency commission = margin)

  Stage: completed →  Confirms revenue recognition (if not already posted)

  Stage: cancelled →  Posts refund/penalty entries as needed

DECOUPLING CONTRACT:
  ✅ Subscribes via EventBus (case.stage.transitioned) — zero coupling to trigger
  ✅ Reads GL account codes from CaseType.meta (plugin-defined config)
  ✅ Posts to GL by publishing InvoiceCreatedEvent — accounting module handles it
  ❌ Never imports from app.modules.accounting
  ❌ Never writes JournalEntry rows directly
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, InvoiceCreatedEvent, get_event_bus
from app.core.events.invoice_payload import build_invoice_created_payload
from app.modules.cases.models.core import Case, CaseType
from app.plugins.travel.services.financials import calculate_booking_financials

logger = logging.getLogger(__name__)
event_bus = get_event_bus()

# Stages that trigger specific GL postings
_CONFIRM_STAGE = "confirmed"
_COMPLETE_STAGE = "completed"
_CANCEL_STAGE = "cancelled"


async def _post_confirmed_entries(
    session,
    case: Case,
    ct: CaseType,
    tenant_id: str,
) -> None:
    """
    Posts on booking confirmation:

      1. Customer Receivable (DR 1200 / CR Revenue 4010) for the sell price
         — records the agency's right to collect from the customer.

      2. Supplier Payable (DR Expense / CR 2100) for the buy price
         — records the agency's obligation to pay suppliers.

    The margin (sell - buy) naturally falls into Revenue account 4010.

    Idempotent: checks case.data["gl_receivable_posted"] before posting.
    """
    if case.data.get("gl_receivable_posted") and case.data.get("gl_payable_posted"):
        logger.info("Travel GL: already posted for case %s — skipping", case.id)
        return

    financials = calculate_booking_financials(
        case_id=str(case.id),
        case_data=case.data,
        meta=ct.meta,
    )

    if financials.total_sell_price <= 0:
        logger.info("Travel GL: zero sell price for case %s — skipping", case.id)
        return

    meta = ct.meta or {}
    receivable_account = meta.get("receivable_gl_account", "1200")
    payable_account = meta.get("payable_gl_account", "2100")
    revenue_account = meta.get("revenue_gl_account", "4010")
    accounting_mode = str(meta.get("accounting_mode", "principal")).strip().lower()

    # ── Entry 1: Customer Receivable / Revenue ────────────────────────────────
    # Principal mode: DR AR / CR Travel Revenue for full sell price (Gross)
    # Agent mode:     DR AR / CR Travel Commission Revenue for net commission only
    if not case.data.get("gl_receivable_posted"):
        is_agent = accounting_mode == "agent"
        rev_amount = financials.commission_amount if is_agent else financials.total_sell_price
        entry_kind = "travel_agent_commission" if is_agent else "travel_customer_receivable"
        narration = (
            f"Travel Booking Commission (Net) — {case.title or str(case.id)}"
            if is_agent
            else f"Travel Booking Receivable — {case.title or str(case.id)}"
        )

        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload=build_invoice_created_payload(
                    source="travel_plugin",
                    source_id=str(case.id),
                    invoice_number=f"TRV-{case.id.hex[:8].upper()}-AR",
                    customer_name=(
                        case.data.get("customer_name_ar")
                        or case.data.get("customer_name")
                        or case.title
                        or str(case.id)
                    ),
                    amount=rev_amount,
                    currency=financials.currency,
                    revenue_account_code=revenue_account,
                    ar_account_code=receivable_account,
                    entry_date=date.today(),
                    description=narration,
                    entry_type=entry_kind,
                    case_stage=_CONFIRM_STAGE,
                    passenger_count=financials.passenger_count,
                    margin=float(financials.total_margin),
                    commission=float(financials.commission_amount),
                ),
            ),
            session=session,
        )
        case.data = {**case.data, "gl_receivable_posted": True}

    # ── Entry 2: Supplier Payable ─────────────────────────────────────────────
    # Principal mode: DR Cost of Sales (5010) / CR Accounts Payable (2100)
    # Agent mode:     DR Accounts Receivable (1200) / CR Accounts Payable (2100)
    #                 (Pass-through liability: customer pays agency for supplier portion)
    if not case.data.get("gl_payable_posted") and financials.total_buy_price > 0:
        is_agent = accounting_mode == "agent"
        debit_account = receivable_account if is_agent else "5010"
        narration = (
            f"Travel Booking Supplier Pass-Through — {case.title or str(case.id)}"
            if is_agent
            else f"Travel Booking Supplier Cost — {case.title or str(case.id)}"
        )

        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload=build_invoice_created_payload(
                    source="travel_plugin",
                    source_id=str(case.id),
                    invoice_number=f"TRV-{case.id.hex[:8].upper()}-AP",
                    customer_name=(
                        case.data.get("customer_name_ar")
                        or case.data.get("customer_name")
                        or case.title
                        or str(case.id)
                    ),
                    amount=financials.total_buy_price,
                    currency=financials.currency,
                    revenue_account_code=payable_account,   # CR: Accounts Payable
                    ar_account_code=debit_account,          # DR: 1200 (Agent) or 5010 (Principal)
                    entry_date=date.today(),
                    description=narration,
                    entry_type="travel_supplier_payable",
                    case_stage=_CONFIRM_STAGE,
                ),
            ),
            session=session,
        )
        case.data = {**case.data, "gl_payable_posted": True}

    if session is not None:
        session.add(case)


async def _post_cancellation_entries(
    session,
    case: Case,
    ct: CaseType,
    tenant_id: str,
) -> None:
    """
    Posts on cancellation:
      - If a receivable was posted, reverse it by the refund_amount
      - Post any penalty_amount as revenue (cancellation fee earned)
    """
    if case.data.get("gl_refund_posted"):
        return

    refund = Decimal(str(case.data.get("refund_amount", "0") or "0"))
    penalty = Decimal(str(case.data.get("penalty_amount", "0") or "0"))

    meta = ct.meta or {}
    revenue_account = meta.get("revenue_gl_account", "4010")
    receivable_account = meta.get("receivable_gl_account", "1200")

    if refund > 0 and case.data.get("gl_receivable_posted"):
        # Reverse the receivable by the refund amount
        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload=build_invoice_created_payload(
                    source="travel_plugin",
                    source_id=str(case.id),
                    invoice_number=f"TRV-{case.id.hex[:8].upper()}-REFUND",
                    customer_name=(
                        case.data.get("customer_name_ar")
                        or case.data.get("customer_name")
                        or case.title
                        or str(case.id)
                    ),
                    amount=refund,
                    currency=case.data.get("currency", "EGP"),
                    revenue_account_code=revenue_account,     # CR: reduce revenue
                    ar_account_code=receivable_account,       # DR: reverse the receivable
                    entry_date=date.today(),
                    description=f"Travel Cancellation Refund — {case.title or str(case.id)}",
                    entry_type="travel_cancellation_refund",
                    case_stage=_CANCEL_STAGE,
                    cancellation_reason=case.data.get("cancellation_reason"),
                ),
            ),
            session=session,
        )

    if penalty > 0:
        # Penalty fee is recognised as revenue
        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload=build_invoice_created_payload(
                    source="travel_plugin",
                    source_id=str(case.id),
                    invoice_number=f"TRV-{case.id.hex[:8].upper()}-PENALTY",
                    customer_name=(
                        case.data.get("customer_name_ar")
                        or case.data.get("customer_name")
                        or case.title
                        or str(case.id)
                    ),
                    amount=penalty,
                    currency=case.data.get("currency", "EGP"),
                    revenue_account_code=revenue_account,
                    ar_account_code=receivable_account,
                    entry_date=date.today(),
                    description=f"Travel Cancellation Penalty Fee — {case.title or str(case.id)}",
                    entry_type="travel_cancellation_penalty",
                    case_stage=_CANCEL_STAGE,
                ),
            ),
            session=session,
        )

    case.data = {**case.data, "gl_refund_posted": True}
    if session is not None:
        session.add(case)


# ── EventBus Handler ───────────────────────────────────────────────────────────


async def _mark_posting_failed(tenant_id: str, case_id_str: str, to_stage: str, exc: Exception) -> None:
    """Best-effort, separate-connection write of the posting_failed flag —
    used whenever we can't trust the session that just raised (it may be in
    a broken state) or don't have one at all. Mirrors the identical helper in
    rental/hospitality/recruitment listeners: without it a failed GL post is
    invisible to anyone not tailing the server log."""
    try:
        async with tenant_session(tenant_id) as fail_session:
            failed_case = await fail_session.get(Case, UUID(case_id_str))
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
            "Travel listener: failed to record posting_failed flag for case %s",
            case_id_str,
        )


@event_bus.subscribe("case.stage.transitioned")
async def handle_travel_stage_transitioned(event: DomainEvent, session: AsyncSession | None = None) -> None:
    """
    Listens for ALL case transitions but acts ONLY on:
      - plugin_key == "travel"
      - to_stage in ("confirmed", "cancelled")

    `session`: EventBus.publish() passes its caller's own session automatically
    whenever this handler's signature accepts a `session` kwarg. We MUST prefer
    that session over opening a fresh one: the Case Engine's transition_case()
    only *flushes* the case's data changes — the caller commits afterwards — so
    a brand-new session on a separate connection would not see them under
    READ COMMITTED. Same pattern as recruitment/rental/hospitality listeners.

    THIS HANDLER USED TO BE BROKEN IN TWO WAYS (live-confirmed 14 Sep 2026):
      1. It opened its own `AsyncSessionLocal()` (isolated transaction), then
      2. ran `await session.execute(f"SET search_path TO {tenant_schema}")` —
         a raw f-string passed straight to AsyncSession.execute(), which
         SQLAlchemy 2.x rejects with ObjectNotExecutableError unless wrapped in
         text(). The exception was caught by the blanket `except Exception` and
         only logged, so `POST /cases/{id}/transition → confirmed` returned a
         clean HTTP 200 while no receivable, no payable and no journal entry
         were ever written. The schema no longer needs setting by hand at all:
         tenant_session() applies schema_translate_map, and the shared-session
         path is already tenant-scoped by the request.
    """
    payload = event.payload

    # Guard: only handle travel plugin events
    if payload.get("plugin_key") != "travel":
        return

    to_stage = payload.get("to_stage")
    if to_stage not in (_CONFIRM_STAGE, _CANCEL_STAGE):
        return

    case_id_str = payload.get("case_id")
    if not case_id_str:
        return

    tenant_id = event.tenant_id
    if not tenant_id:
        logger.warning(
            "Travel listener: event for case %s carries no tenant_id — cannot "
            "resolve tenant schema, skipping financial posting.", case_id_str,
        )
        return

    async def _dispatch(active_session) -> None:
        case = await active_session.get(Case, UUID(case_id_str))
        if not case:
            logger.warning("Travel listener: Case %s not found", case_id_str)
            return
        ct = await active_session.get(CaseType, case.case_type_id)
        if not ct:
            logger.warning("Travel listener: CaseType not found for case %s", case_id_str)
            return

        if to_stage == _CONFIRM_STAGE:
            await _post_confirmed_entries(active_session, case, ct, tenant_id)
        elif to_stage == _CANCEL_STAGE:
            await _post_cancellation_entries(active_session, case, ct, tenant_id)

    if session is not None:
        # Fast path — reuse the caller's already tenant-scoped session.
        try:
            await _dispatch(session)
            logger.info(
                "Travel financial hook completed for case %s → stage %s (shared-session path)",
                case_id_str, to_stage,
            )
            # No manual commit/rollback — the caller owns the transaction.
        except Exception as exc:
            logger.exception(
                "Travel listener failed for case %s stage %s (shared-session path) "
                "— marking posting_failed on the case for visibility.",
                case_id_str, to_stage,
            )
            await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
        return

    # Fallback path — no session supplied (e.g. outbox-worker driven dispatch).
    try:
        async with tenant_session(tenant_id) as fresh_session:
            await _dispatch(fresh_session)
        logger.info(
            "Travel financial hook completed for case %s → stage %s",
            case_id_str, to_stage,
        )
    except Exception as exc:
        logger.exception(
            "Travel listener failed for case %s stage %s", case_id_str, to_stage,
        )
        await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
