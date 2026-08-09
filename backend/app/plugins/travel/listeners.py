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

from app.core.db.database import AsyncSessionLocal
from app.core.events.event_bus import DomainEvent, InvoiceCreatedEvent, get_event_bus
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

    # ── Entry 1: Customer Receivable ──────────────────────────────────────────
    # DR Accounts Receivable / CR Travel Revenue
    if not case.data.get("gl_receivable_posted"):
        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload={
                    "source": "travel_plugin",
                    "source_id": str(case.id),
                    "entry_type": "customer_receivable",
                    "description": f"Travel Booking Receivable — {case.title or str(case.id)}",
                    "amount": float(financials.total_sell_price),
                    "currency": financials.currency,
                    "revenue_account_code": revenue_account,
                    "receivable_account_code": receivable_account,
                    "entry_date": date.today().isoformat(),
                    "case_stage": _CONFIRM_STAGE,
                    "passenger_count": financials.passenger_count,
                    "margin": float(financials.total_margin),
                    "commission": float(financials.commission_amount),
                },
            ),
            session=session,
        )
        case.data = {**case.data, "gl_receivable_posted": True}

    # ── Entry 2: Supplier Payable ─────────────────────────────────────────────
    # DR Cost of Sales / CR Accounts Payable
    if not case.data.get("gl_payable_posted") and financials.total_buy_price > 0:
        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload={
                    "source": "travel_plugin",
                    "source_id": str(case.id),
                    "entry_type": "supplier_payable",
                    "description": f"Travel Booking Supplier Cost — {case.title or str(case.id)}",
                    "amount": float(financials.total_buy_price),
                    "currency": financials.currency,
                    "revenue_account_code": payable_account,      # CR: AP
                    "receivable_account_code": "5010",            # DR: COGS
                    "entry_date": date.today().isoformat(),
                    "case_stage": _CONFIRM_STAGE,
                },
            ),
            session=session,
        )
        case.data = {**case.data, "gl_payable_posted": True}

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
                payload={
                    "source": "travel_plugin",
                    "source_id": str(case.id),
                    "entry_type": "cancellation_refund",
                    "description": f"Travel Cancellation Refund — {case.title or str(case.id)}",
                    "amount": float(refund),
                    "currency": case.data.get("currency", "EGP"),
                    "revenue_account_code": receivable_account,   # DR: reverse the receivable
                    "receivable_account_code": revenue_account,   # CR: reduce revenue
                    "entry_date": date.today().isoformat(),
                    "case_stage": _CANCEL_STAGE,
                    "cancellation_reason": case.data.get("cancellation_reason"),
                },
            ),
            session=session,
        )

    if penalty > 0:
        # Penalty fee is recognised as revenue
        await event_bus.publish(
            InvoiceCreatedEvent(
                tenant_id=tenant_id,
                payload={
                    "source": "travel_plugin",
                    "source_id": str(case.id),
                    "entry_type": "cancellation_penalty",
                    "description": f"Travel Cancellation Penalty Fee — {case.title or str(case.id)}",
                    "amount": float(penalty),
                    "currency": case.data.get("currency", "EGP"),
                    "revenue_account_code": revenue_account,
                    "receivable_account_code": receivable_account,
                    "entry_date": date.today().isoformat(),
                    "case_stage": _CANCEL_STAGE,
                },
            ),
            session=session,
        )

    case.data = {**case.data, "gl_refund_posted": True}
    session.add(case)


# ── EventBus Handler ───────────────────────────────────────────────────────────


@event_bus.subscribe("case.stage.transitioned")
async def handle_travel_stage_transitioned(event: DomainEvent) -> None:
    """
    Listens for ALL case transitions but acts ONLY on:
      - plugin_key == "travel"
      - to_stage in ("confirmed", "cancelled")
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

    async with AsyncSessionLocal() as session:
        try:
            tenant_id = event.tenant_id
            tenant_schema = f"tenant_{tenant_id.replace('-', '')}"
            await session.execute(f"SET search_path TO {tenant_schema}")

            case = await session.get(Case, UUID(case_id_str))
            if not case:
                logger.warning("Travel listener: Case %s not found", case_id_str)
                return

            ct = await session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Travel listener: CaseType not found for case %s", case_id_str)
                return

            if to_stage == _CONFIRM_STAGE:
                await _post_confirmed_entries(session, case, ct, tenant_id)
            elif to_stage == _CANCEL_STAGE:
                await _post_cancellation_entries(session, case, ct, tenant_id)

            await session.commit()
            logger.info(
                "Travel financial hook completed for case %s → stage %s",
                case_id_str, to_stage,
            )

        except Exception:
            logger.exception(
                "Travel listener failed for case %s stage %s",
                case_id_str, to_stage,
            )
            await session.rollback()
