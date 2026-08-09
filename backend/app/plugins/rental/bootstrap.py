"""
app/plugins/rental/bootstrap.py — Vehicle Rental Plugin Configuration Injector

Injects the 'vehicle_rental' CaseType into the Generic Case Engine.
The engine's Resource table stores Vehicles; the double-booking exclusion logic
already lives in the core engine's _check_resource_availability().

DECOUPLING CONTRACT:
  ✅ Writes CaseType DATA rows only — never patches core engine code
  ✅ Sets meta["uses_resource"] = True to signal the engine to enforce
     the (resource_id, start_date, end_date) overlap lock
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models.core import CaseType

# ── Stage Definitions ──────────────────────────────────────────────────────────

VEHICLE_RENTAL_STAGES: list[dict] = [
    {
        "id": "reserved",
        "label": "Reserved / Pending Pickup",
        "label_ar": "محجوز / في انتظار الاستلام",
        "order": 1,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["renter_name", "daily_rate", "driver_license_number"],
            "properties": {
                "renter_name": {"type": "string", "maxLength": 255},
                "renter_name_ar": {"type": "string", "maxLength": 255},
                "renter_phone": {"type": "string", "maxLength": 30},
                "driver_license_number": {"type": "string", "maxLength": 100},
                "driver_license_expiry": {"type": "string", "format": "date"},
                
                "daily_rate": {"type": "number", "minimum": 0},
                "currency": {"type": "string", "default": "EGP"},
                "mileage_limit_per_day": {"type": "number", "minimum": 0, "description": "Km per day. 0 = unlimited"},
                "extra_mileage_rate": {"type": "number", "minimum": 0, "description": "Cost per extra Km"},
                
                "insurance_type": {
                    "type": "string",
                    "enum": ["basic", "comprehensive", "premium"],
                    "default": "basic",
                },
                "deposit_amount": {"type": "number", "minimum": 0},
                
                "pickup_location": {"type": "string"},
                "return_location": {"type": "string"},
                
                "notes": {"type": "string"},
            },
        },
    },
    {
        "id": "picked_up",
        "label": "Picked Up (Active)",
        "label_ar": "تم الاستلام (نشط)",
        "order": 2,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["pickup_actual"],
            "properties": {
                "pickup_actual": {"type": "string", "format": "date-time"},
                "handover_by": {"type": "string"},
                "pickup_inspection_completed": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "returned",
        "label": "Returned",
        "label_ar": "تم الإرجاع",
        "order": 3,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["return_actual"],
            "properties": {
                "return_actual": {"type": "string", "format": "date-time"},
                "received_by": {"type": "string"},
                "return_inspection_completed": {"type": "boolean", "default": False},
                
                # Computed by diff engine
                "total_rental_charge": {"type": "number"},
                "extra_mileage_charge": {"type": "number"},
                "fuel_penalty": {"type": "number"},
                "damage_penalty": {"type": "number"},
                "grand_total": {"type": "number"},
                "gl_revenue_posted": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "closed",
        "label": "Closed / Settled",
        "label_ar": "مغلق / تم التسوية",
        "order": 4,
        "is_terminal": True,
        "terminal_status": "CLOSED",
        "schema": {
            "type": "object",
            "properties": {
                "closure_notes": {"type": "string"},
                "deposit_returned": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "cancelled",
        "label": "Cancelled",
        "label_ar": "ملغي",
        "order": 5,
        "is_terminal": True,
        "terminal_status": "CANCELLED",
        "schema": {
            "type": "object",
            "required": ["cancellation_reason"],
            "properties": {
                "cancellation_reason": {"type": "string"},
                "cancellation_penalty": {"type": "number", "minimum": 0},
                "gl_penalty_posted": {"type": "boolean", "default": False},
            },
        },
    },
]

RENTAL_CONTACT_ROLE_SCHEMAS: dict[str, dict] = {
    "renter": {
        "description": "Primary driver / renter.",
        "required": ["driver_license_number"],
        "properties": {
            "driver_license_number": {"type": "string"},
            "license_expiry": {"type": "string", "format": "date"},
            "id_number": {"type": "string"},
        },
    },
    "corporate": {
        "description": "Corporate account renting the vehicle.",
        "properties": {
            "company_name": {"type": "string"},
            "tax_number": {"type": "string"},
        },
    },
}


async def bootstrap_rental_case_type(session: AsyncSession) -> CaseType:
    """
    Idempotent: inserts the 'vehicle_rental' CaseType.
    """
    result = await session.execute(
        select(CaseType).where(CaseType.code == "vehicle_rental")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    case_type = CaseType(
        code="vehicle_rental",
        name="Vehicle Rental",
        name_ar="تأجير السيارات",
        plugin_key="rental",
        initial_stage="reserved",
        stages=VEHICLE_RENTAL_STAGES,
        meta={
            "contact_role_schemas": RENTAL_CONTACT_ROLE_SCHEMAS,
            "uses_resource": True,
            "resource_type": "vehicle",
            # GL account codes
            "revenue_gl_account": "4020",        # Rental Revenue
            "receivable_gl_account": "1200",     # Accounts Receivable
            "tax_rate": 0.14,                    # 14% VAT (Egypt standard)
            # Default penalties
            "fuel_shortage_penalty": 200.0,      # Default penalty per 1/4 tank missing
        },
    )
    session.add(case_type)
    await session.flush()
    return case_type
