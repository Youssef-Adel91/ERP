"""
app/plugins/rental/services/inspection.py — Condition-at-Handover Engine

Diffs pickup and return inspections to compute penalties for fuel shortage,
extra mileage, and flags new damage.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.plugins.rental.models.inspection import FuelLevel, InspectionType, VehicleInspection

# Map string enum to numerical quarters for math
_FUEL_VALUES = {
    FuelLevel.EMPTY: 0,
    FuelLevel.QUARTER: 1,
    FuelLevel.HALF: 2,
    FuelLevel.THREE_QUARTERS: 3,
    FuelLevel.FULL: 4,
}


class InspectionDiff(BaseModel):
    pickup_mileage: int
    return_mileage: int
    driven_distance: int
    extra_mileage: int
    extra_mileage_charge: Decimal

    pickup_fuel: str
    return_fuel: str
    fuel_shortage_quarters: int
    fuel_penalty: Decimal
    
    new_damages: list[dict]
    
    total_penalties: Decimal


async def get_inspection(session: AsyncSession, case_id: uuid.UUID, ins_type: InspectionType) -> VehicleInspection | None:
    stmt = select(VehicleInspection).where(
        VehicleInspection.case_id == case_id,
        VehicleInspection.inspection_type == ins_type,
    )
    return (await session.scalars(stmt)).first()


async def diff_inspections(
    session: AsyncSession,
    case_id: uuid.UUID,
    case_data: dict[str, Any],
    meta: dict[str, Any],
) -> InspectionDiff | None:
    """
    Computes the difference between pickup and return inspections.
    Requires both inspections to exist.
    """
    pickup = await get_inspection(session, case_id, InspectionType.PICKUP)
    return_ins = await get_inspection(session, case_id, InspectionType.RETURN)

    if not pickup or not return_ins:
        return None

    # 1. Mileage diffing
    driven_distance = max(0, int(return_ins.mileage) - int(pickup.mileage))
    from datetime import date
    try:
        ci = date.fromisoformat(case_data.get("pickup_actual", "")[:10])
        co = date.fromisoformat(case_data.get("return_actual", "")[:10])
        days = max(1, (co - ci).days)
    except Exception:
        days = 1

    limit_per_day = float(case_data.get("mileage_limit_per_day", 0))
    extra_rate = Decimal(str(case_data.get("extra_mileage_rate", "0")))
    
    extra_mileage = 0
    extra_charge = Decimal("0")
    if limit_per_day > 0:
        total_limit = int(limit_per_day * days)
        if driven_distance > total_limit:
            extra_mileage = driven_distance - total_limit
            extra_charge = Decimal(str(extra_mileage)) * extra_rate

    # 2. Fuel diffing
    p_fuel = _FUEL_VALUES[pickup.fuel_level]
    r_fuel = _FUEL_VALUES[return_ins.fuel_level]
    shortage = max(0, p_fuel - r_fuel)
    fuel_penalty_rate = Decimal(str(meta.get("fuel_shortage_penalty", "200.0")))
    fuel_penalty = Decimal(str(shortage)) * fuel_penalty_rate

    # 3. Damage diffing
    p_damages = pickup.damage_notes or []
    r_damages = return_ins.damage_notes or []
    # Identify damages in return that are not in pickup (simple heuristic by location/type)
    p_keys = {f"{d.get('location')}_{d.get('type')}" for d in p_damages}
    new_damages = [d for d in r_damages if f"{d.get('location')}_{d.get('type')}" not in p_keys]

    total_penalties = extra_charge + fuel_penalty

    return InspectionDiff(
        pickup_mileage=int(pickup.mileage),
        return_mileage=int(return_ins.mileage),
        driven_distance=driven_distance,
        extra_mileage=extra_mileage,
        extra_mileage_charge=extra_charge,
        pickup_fuel=pickup.fuel_level.value,
        return_fuel=return_ins.fuel_level.value,
        fuel_shortage_quarters=shortage,
        fuel_penalty=fuel_penalty,
        new_damages=new_damages,
        total_penalties=total_penalties,
    )
