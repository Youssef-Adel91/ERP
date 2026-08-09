"""
app/plugins/hospitality/bootstrap.py — Hospitality Plugin Configuration Injector

Injects the 'room_reservation' CaseType into the Generic Case Engine.
The engine's Resource table stores Rooms; the double-booking exclusion logic
already lives in the core engine's _check_resource_availability().

DECOUPLING CONTRACT:
  ✅ Writes CaseType DATA rows only — never patches core engine code
  ✅ Sets meta["uses_resource"] = True to signal the engine to enforce
     the (resource_id, start_date, end_date) overlap lock
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models.core import CaseType

# ── Stage Definitions ──────────────────────────────────────────────────────────
#
# Case.resource_id → Room (a Resource row with resource_type="room")
# Case.start_date  → Check-in date
# Case.end_date    → Check-out date
# Case.data        → guest details, pricing, and folio summary

ROOM_RESERVATION_STAGES: list[dict] = [
    {
        "id": "booked",
        "label": "Booked / Pending Confirmation",
        "label_ar": "محجوز / في الانتظار",
        "order": 1,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["guest_name", "daily_rate", "guest_count"],
            "properties": {
                # Primary guest details
                "guest_name": {"type": "string", "maxLength": 255},
                "guest_name_ar": {"type": "string", "maxLength": 255},
                "guest_phone": {"type": "string", "maxLength": 30},
                "guest_email": {"type": "string", "format": "email"},
                "guest_nationality": {"type": "string", "maxLength": 100},
                "guest_id_number": {"type": "string", "maxLength": 50},
                "guest_id_type": {
                    "type": "string",
                    "enum": ["national_id", "passport", "driving_licence"],
                    "default": "national_id",
                },
                "guest_count": {"type": "integer", "minimum": 1},
                "children_count": {"type": "integer", "minimum": 0, "default": 0},

                # Pricing
                "daily_rate": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Price per night in the booking currency",
                },
                "currency": {"type": "string", "default": "EGP"},

                # Breakfast and board configuration (drives folio auto-charges)
                "board_type": {
                    "type": "string",
                    "enum": ["room_only", "bed_breakfast", "half_board", "full_board", "all_inclusive"],
                    "default": "room_only",
                },
                "breakfast_rate_per_person": {"type": "number", "minimum": 0},

                # Channel / source
                "booking_source": {
                    "type": "string",
                    "enum": ["direct", "phone", "booking.com", "airbnb", "agoda", "other"],
                    "default": "direct",
                },
                "booking_reference": {"type": "string", "maxLength": 100},

                # GL flags (set by financial listener — never set by user)
                "gl_revenue_posted": {"type": "boolean", "default": False},
                "folio_total": {"type": "number"},

                "notes": {"type": "string", "maxLength": 2000},
            },
        },
    },
    {
        "id": "confirmed",
        "label": "Confirmed",
        "label_ar": "مؤكد",
        "order": 2,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "properties": {
                "confirmation_reference": {"type": "string", "maxLength": 100},
                "deposit_amount": {"type": "number", "minimum": 0},
                "deposit_method": {
                    "type": "string",
                    "enum": ["cash", "card", "bank_transfer", "cheque"],
                },
                "confirmed_at": {"type": "string", "format": "date-time"},
            },
        },
    },
    {
        "id": "checked_in",
        "label": "Checked In",
        "label_ar": "تم تسجيل الدخول",
        "order": 3,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["checkin_actual"],
            "properties": {
                "checkin_actual": {"type": "string", "format": "date-time"},
                "key_card_number": {"type": "string", "maxLength": 50},
                "checked_in_by": {"type": "string"},
            },
        },
    },
    {
        "id": "checked_out",
        "label": "Checked Out",
        "label_ar": "تم تسجيل المغادرة",
        "order": 4,
        "is_terminal": False,   # Not terminal — allow closing the folio
        "schema": {
            "type": "object",
            "required": ["checkout_actual"],
            "properties": {
                "checkout_actual": {"type": "string", "format": "date-time"},
                "payment_method": {
                    "type": "string",
                    "enum": ["cash", "card", "bank_transfer", "cheque", "credit"],
                },
                "final_folio_total": {"type": "number"},
                "checked_out_by": {"type": "string"},
            },
        },
    },
    {
        "id": "closed",
        "label": "Closed / Settled",
        "label_ar": "مغلق / تم التسوية",
        "order": 5,
        "is_terminal": True,
        "terminal_status": "CLOSED",
        "schema": {
            "type": "object",
            "properties": {
                "closure_notes": {"type": "string"},
            },
        },
    },
    {
        "id": "cancelled",
        "label": "Cancelled",
        "label_ar": "ملغي",
        "order": 6,
        "is_terminal": True,
        "terminal_status": "CANCELLED",
        "schema": {
            "type": "object",
            "required": ["cancellation_reason"],
            "properties": {
                "cancellation_reason": {"type": "string"},
                "cancellation_penalty": {"type": "number", "minimum": 0},
                "refund_amount": {"type": "number", "minimum": 0},
                "gl_refund_posted": {"type": "boolean", "default": False},
            },
        },
    },
]

HOSPITALITY_CONTACT_ROLE_SCHEMAS: dict[str, dict] = {
    "guest": {
        "description": "The primary guest / room occupant.",
        "required": ["id_number"],
        "properties": {
            "id_number": {"type": "string"},
            "id_type": {"type": "string", "enum": ["national_id", "passport", "driving_licence"]},
            "id_expiry": {"type": "string", "format": "date"},
        },
    },
    "corporate": {
        "description": "Corporate account for business reservations.",
        "properties": {
            "company_name": {"type": "string"},
            "tax_number": {"type": "string"},
            "purchase_order": {"type": "string"},
        },
    },
}


async def bootstrap_hospitality_case_type(session: AsyncSession) -> CaseType:
    """
    Idempotent: inserts the 'room_reservation' CaseType if it does not exist.
    Sets uses_resource=True so the engine enforces the Room overlap lock.
    """
    result = await session.execute(
        select(CaseType).where(CaseType.code == "room_reservation")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    case_type = CaseType(
        code="room_reservation",
        name="Room Reservation",
        name_ar="حجز غرفة فندقية",
        plugin_key="hospitality",
        initial_stage="booked",
        stages=ROOM_RESERVATION_STAGES,
        meta={
            "contact_role_schemas": HOSPITALITY_CONTACT_ROLE_SCHEMAS,
            # CRITICAL: tells the engine to enforce resource overlap lock
            "uses_resource": True,
            "resource_type": "room",
            # GL account codes
            "revenue_gl_account": "4010",        # Hotel Revenue
            "receivable_gl_account": "1200",     # Accounts Receivable
            "tax_rate": 0.14,                    # 14% VAT (Egypt standard)
            "service_charge_rate": 0.12,         # 12% service charge
        },
    )
    session.add(case_type)
    await session.flush()
    return case_type
