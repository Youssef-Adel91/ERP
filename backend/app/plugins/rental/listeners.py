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

from app.core.db.database import AsyncSessionLocal
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

    await event_bus.publish(
        InvoiceCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "source": "rental_plugin",
                "source_id": str(case.id),
                "entry_type": "vehicle_rental_revenue",
                "description": f"Vehicle Rental Return — {case.data.get('renter_name_ar') or case.data.get('renter_name')}",
                "amount": float(grand_total),
                "currency": case.data.get("currency", "EGP"),
                "revenue_account_code": revenue_account,
                "receivable_account_code": receivable_account,
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


@event_bus.subscribe("case.stage.transitioned")
async def handle_rental_stage_transitioned(event: DomainEvent) -> None:
    payload = event.payload
    if payload.get("plugin_key") != "rental":
        return

    to_stage = payload.get("to_stage")
    if to_stage != _RETURN_STAGE:
        return

    case_id_str = payload.get("case_id")
    async with AsyncSessionLocal() as session:
        try:
            tenant_id = event.tenant_id
            tenant_schema = f"tenant_{tenant_id.replace('-', '')}"
            await session.execute(f"SET search_path TO {tenant_schema}")

            case = await session.get(Case, uuid.UUID(case_id_str))
            if not case: return
            
            ct = await session.get(CaseType, case.case_type_id)
            if not ct: return

            await _post_return_revenue(session, case, ct, tenant_id)
            await session.commit()
        except Exception:
            logger.exception("Rental listener failed")
            await session.rollback()
