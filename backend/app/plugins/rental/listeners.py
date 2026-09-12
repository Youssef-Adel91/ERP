"""
app/plugins/rental/listeners.py — Vehicle Rental Financial Hooks

Subscribes to CaseStageTransitionedEvent (plugin_key = "rental").

returned →  diffs inspections, calculates total (rental + extra km + fuel penalty),
            and publishes InvoiceCreatedEvent to GL.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import tenant_session
from app.core.events.event_bus import DomainEvent, InvoiceCreatedEvent, get_event_bus
from app.modules.cases.models.core import Case, CaseType
from app.plugins.rental.services.inspection import diff_inspections

logger = logging.getLogger(__name__)
event_bus = get_event_bus()

_RETURN_STAGE = "returned"


async def _post_return_revenue(
    session,
    case: Case,
    ct: CaseType,
    tenant_id: str,
) -> None:
    if case.data.get("gl_revenue_posted"):
        return

    meta = ct.meta or {}
    
    # Run the inspection diff
    diff = await diff_inspections(session, case.id, case.data, meta)
    
    # Calculate base rental charge
    from datetime import date
    try:
        ci = date.fromisoformat(case.data.get("pickup_actual", "")[:10])
        co = date.fromisoformat(case.data.get("return_actual", "")[:10])
        days = max(1, (co - ci).days)
    except Exception:
        days = 1

    daily_rate = Decimal(str(case.data.get("daily_rate", "0")))
    base_charge = daily_rate * Decimal(days)
    
    # Apply penalties if diff exists
    extra_mileage_charge = diff.extra_mileage_charge if diff else Decimal("0")
    fuel_penalty = diff.fuel_penalty if diff else Decimal("0")
    damage_penalty = Decimal(str(case.data.get("damage_penalty", "0")))
    
    subtotal = base_charge + extra_mileage_charge + fuel_penalty + damage_penalty
    tax_rate = Decimal(str(meta.get("tax_rate", "0.14")))
    tax_amount = subtotal * tax_rate
    grand_total = subtotal + tax_amount

    if grand_total <= 0:
        return

    revenue_account = meta.get("revenue_gl_account", "4020")
    receivable_account = meta.get("receivable_gl_account", "1200")

    line_items = [
        {"description": f"الإيجار ({days} يوم)", "amount": float(base_charge)}
    ]
    if extra_mileage_charge > 0:
        line_items.append({"description": f"رسوم كيلومتر إضافي ({diff.extra_mileage} كم)", "amount": float(extra_mileage_charge)})
    if fuel_penalty > 0:
        line_items.append({"description": f"غرامة وقود ({diff.fuel_shortage_quarters}/4)", "amount": float(fuel_penalty)})
    if damage_penalty > 0:
        line_items.append({"description": "غرامة أضرار", "amount": float(damage_penalty)})
    if tax_amount > 0:
        line_items.append({"description": "ضريبة القيمة المضافة", "amount": float(tax_amount)})

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
    customer_name = case.data.get("renter_name_ar") or case.data.get("renter_name") or str(case.id)
    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "source": "rental_plugin",
                "source_id": str(case.id),
                "invoice_id": str(case.id),
                "invoice_number": f"RENT-{case.id.hex[:8].upper()}-RET",
                "customer_name": customer_name,
                "entry_type": "vehicle_rental_revenue",
                "description": f"Vehicle Rental Return — {customer_name}",
                "amount": float(grand_total),
                "currency": case.data.get("currency", "EGP"),
                "revenue_account_code": revenue_account,
                "receivable_account_code": receivable_account,
                "ar_account_code": receivable_account,
                "entry_date": date.today().isoformat(),
                "line_items": line_items,
            },
        ),
        session=session,
    )

    case.data = {
        **case.data,
        "gl_revenue_posted": True,
        "total_rental_charge": float(base_charge),
        "extra_mileage_charge": float(extra_mileage_charge),
        "fuel_penalty": float(fuel_penalty),
        "grand_total": float(grand_total),
    }
    session.add(case)


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
            "Rental listener: failed to record posting_failed flag for case %s",
            case_id_str,
        )


@event_bus.subscribe("case.stage.transitioned")
async def handle_rental_stage_transitioned(event: DomainEvent, session: AsyncSession | None = None) -> None:
    """
    `session`: EventBus.publish() passes its caller's own session automatically
    whenever this handler's signature accepts a `session` kwarg. We MUST prefer
    that session over opening a fresh tenant_session() when one is available:
    the Case Engine's transition_case() only *flushes* the case's data changes
    (e.g. return-inspection fields set in the very same API call that moves
    the case to "returned") — the caller commits afterwards. A brand-new
    tenant_session() opens a separate DB connection/transaction, and under
    Postgres's default READ COMMITTED isolation it would NOT see those
    flushed-but-uncommitted changes. See recruitment/listeners.py for the
    reference implementation of this pattern.
    """
    payload = event.payload
    if payload.get("plugin_key") != "rental":
        return

    to_stage = payload.get("to_stage")
    if to_stage != _RETURN_STAGE:
        return

    case_id_str = payload.get("case_id")
    if not case_id_str:
        return

    tenant_id = event.tenant_id
    if not tenant_id:
        logger.warning(
            "Rental listener: event for case %s carries no tenant_id — cannot "
            "resolve tenant schema, skipping financial posting.", case_id_str,
        )
        return

    if session is not None:
        # Fast path — reuse the caller's already tenant-scoped session so we
        # can see flushed-but-uncommitted changes from the same request.
        try:
            case = await session.get(Case, uuid.UUID(case_id_str))
            if not case:
                logger.warning("Rental listener: Case %s not found", case_id_str)
                return
            ct = await session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Rental listener: CaseType not found for case %s", case_id_str)
                return

            await _post_return_revenue(session, case, ct, tenant_id)
            logger.info(
                "Rental financial hook completed for case %s → %s (shared-session path)",
                case_id_str, to_stage,
            )
            # No manual commit/rollback — the caller owns this session's
            # transaction boundary.
        except Exception as exc:
            logger.exception(
                "Rental listener failed for case %s stage %s (shared-session "
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
                logger.warning("Rental listener: Case %s not found", case_id_str)
                return

            ct = await fresh_session.get(CaseType, case.case_type_id)
            if not ct:
                logger.warning("Rental listener: CaseType not found for case %s", case_id_str)
                return

            await _post_return_revenue(fresh_session, case, ct, tenant_id)
        logger.info(
            "Rental financial hook completed for case %s → %s", case_id_str, to_stage
        )
    except Exception as exc:
        logger.exception("Rental listener failed for case %s", case_id_str)
        await _mark_posting_failed(tenant_id, case_id_str, to_stage, exc)
