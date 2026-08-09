"""
app/plugins/travel/bootstrap.py — Travel & Tourism Booking Plugin Configuration Injector

DECOUPLING CONTRACT:
  ✅ Imports ONLY from app.core and app.modules.cases (CaseType model)
  ✅ Injects CaseType configuration as DATA rows — never patches core engine code
  ❌ Never alters core engine logic
  ❌ Never imports from app.modules.accounting directly

Usage:
    Called once per tenant during plugin activation. Idempotent.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models.core import CaseType

# ── Stage Definitions ──────────────────────────────────────────────────────────
#
# case.data top-level keys evolve across stages:
#   All stages:   passenger_manifest, services, currency
#   quotation:    buy_price, sell_price, margin, margin_pct
#   confirmed:    confirmation_reference, payment_terms
#   ticketed:     ticket_numbers (array), ticket_issued_at
#   completed:    travel_date_actual, feedback_score
#   cancelled:    cancellation_reason, refund_amount, penalty_amount

TRAVEL_BOOKING_STAGES: list[dict] = [
    {
        "id": "inquiry",
        "label": "Inquiry Received",
        "label_ar": "استفسار واردة",
        "order": 1,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["customer_name", "destination", "travel_date_requested"],
            "properties": {
                # Customer intent
                "customer_name": {"type": "string", "maxLength": 255},
                "customer_name_ar": {"type": "string", "maxLength": 255},
                "destination": {"type": "string", "maxLength": 255},
                "origin": {"type": "string", "maxLength": 255},
                "travel_date_requested": {"type": "string", "format": "date"},
                "return_date_requested": {"type": "string", "format": "date"},
                "group_size": {"type": "integer", "minimum": 1},
                "trip_type": {
                    "type": "string",
                    "enum": ["one_way", "round_trip", "multi_city", "package"],
                },
                # Passenger manifest — array of passenger objects
                # Fully validated at the quotation stage when passports are collected
                "passenger_manifest": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["full_name"],
                        "properties": {
                            "full_name": {"type": "string"},
                            "full_name_ar": {"type": "string"},
                            "passport_number": {"type": "string"},
                            "passport_expiry": {"type": "string", "format": "date"},
                            "date_of_birth": {"type": "string", "format": "date"},
                            "nationality": {"type": "string"},
                            "gender": {"type": "string", "enum": ["male", "female"]},
                            "passenger_type": {
                                "type": "string",
                                "enum": ["adult", "child", "infant"],
                                "default": "adult",
                            },
                        },
                    },
                },
                # Services requested — array of service line items
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["service_type"],
                        "properties": {
                            "service_type": {
                                "type": "string",
                                "enum": [
                                    "flight",
                                    "hotel",
                                    "transfer",
                                    "visa",
                                    "travel_insurance",
                                    "excursion",
                                    "car_rental",
                                    "other",
                                ],
                            },
                            "supplier_id": {"type": "string"},
                            "supplier_name": {"type": "string"},
                            "description": {"type": "string"},
                            "buy_price": {"type": "number", "minimum": 0},
                            "sell_price": {"type": "number", "minimum": 0},
                            "currency": {"type": "string", "default": "EGP"},
                            "quantity": {"type": "integer", "minimum": 1, "default": 1},
                        },
                    },
                },
                "currency": {"type": "string", "default": "EGP"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "id": "quotation",
        "label": "Quotation Sent",
        "label_ar": "تم إرسال العرض",
        "order": 2,
        "is_terminal": False,
        "allow_rollback": True,
        "schema": {
            "type": "object",
            "required": ["buy_price", "sell_price", "quotation_reference"],
            "properties": {
                # Financial summary for the whole booking
                "quotation_reference": {"type": "string", "maxLength": 100},
                "buy_price": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Total cost from all suppliers (cost of goods sold)",
                },
                "sell_price": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Amount billed to the customer",
                },
                "margin": {
                    "type": "number",
                    "description": "sell_price - buy_price (computed, not user-entered)",
                },
                "margin_pct": {
                    "type": "number",
                    "description": "margin / sell_price * 100",
                },
                "currency": {"type": "string", "default": "EGP"},
                "valid_until": {"type": "string", "format": "date"},
                "quotation_sent_at": {"type": "string", "format": "date-time"},
            },
        },
    },
    {
        "id": "confirmed",
        "label": "Booking Confirmed",
        "label_ar": "تم التأكيد",
        "order": 3,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["confirmation_reference"],
            "properties": {
                "confirmation_reference": {"type": "string", "maxLength": 100},
                "payment_terms": {
                    "type": "string",
                    "enum": ["full_upfront", "deposit_balance", "credit"],
                    "default": "full_upfront",
                },
                "deposit_amount": {"type": "number", "minimum": 0},
                "deposit_due_date": {"type": "string", "format": "date"},
                "balance_due_date": {"type": "string", "format": "date"},
                # GL flags set by the financial listener — NEVER set by user
                "gl_receivable_posted": {"type": "boolean", "default": False},
                "gl_payable_posted": {"type": "boolean", "default": False},
                "confirmed_at": {"type": "string", "format": "date-time"},
            },
        },
    },
    {
        "id": "ticketed",
        "label": "Tickets Issued",
        "label_ar": "تم إصدار التذاكر",
        "order": 4,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["ticket_numbers"],
            "properties": {
                "ticket_numbers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "ticket_issued_at": {"type": "string", "format": "date-time"},
                "airline_pnr": {"type": "string", "maxLength": 10},
                "hotel_voucher_ref": {"type": "string", "maxLength": 100},
            },
        },
    },
    {
        "id": "completed",
        "label": "Trip Completed",
        "label_ar": "اكتملت الرحلة",
        "order": 5,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "properties": {
                "travel_date_actual": {"type": "string", "format": "date"},
                "return_date_actual": {"type": "string", "format": "date"},
                "feedback_score": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                },
                "feedback_notes": {"type": "string"},
                "gl_revenue_posted": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "closed",
        "label": "Closed",
        "label_ar": "مغلق",
        "order": 6,
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
        "order": 7,
        "is_terminal": True,
        "terminal_status": "CANCELLED",
        "allow_rollback": False,
        "schema": {
            "type": "object",
            "required": ["cancellation_reason"],
            "properties": {
                "cancellation_reason": {"type": "string"},
                "refund_amount": {"type": "number", "minimum": 0},
                "penalty_amount": {"type": "number", "minimum": 0},
                "cancelled_by": {"type": "string"},
                "gl_refund_posted": {"type": "boolean", "default": False},
            },
        },
    },
]

# ── Contact Role Schemas ───────────────────────────────────────────────────────

TRAVEL_CONTACT_ROLE_SCHEMAS: dict[str, dict] = {
    "lead_passenger": {
        "description": "Primary booking contact / trip leader.",
        "required": ["passport_number", "nationality"],
        "properties": {
            "passport_number": {"type": "string"},
            "passport_expiry": {"type": "string", "format": "date"},
            "nationality": {"type": "string"},
            "frequent_flyer": {"type": "string"},
        },
    },
    "supplier": {
        "description": "Airline, hotel, or other service supplier for this booking.",
        "properties": {
            "supplier_type": {
                "type": "string",
                "enum": ["airline", "hotel", "transfer", "insurance", "other"],
            },
            "booking_reference": {"type": "string"},
            "contract_rate": {"type": "number"},
        },
    },
    "corporate_client": {
        "description": "Corporate account booking on behalf of employees.",
        "required": ["company_registration_number"],
        "properties": {
            "company_registration_number": {"type": "string"},
            "cost_center": {"type": "string"},
            "purchase_order": {"type": "string"},
        },
    },
}


async def bootstrap_travel_case_type(session: AsyncSession) -> CaseType:
    """
    Idempotent: inserts the 'travel_booking' CaseType if it does not already exist.
    Called once per tenant during plugin activation.
    """
    result = await session.execute(
        select(CaseType).where(CaseType.code == "travel_booking")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    case_type = CaseType(
        code="travel_booking",
        name="Travel & Tourism Booking",
        name_ar="حجز السياحة والسفر",
        plugin_key="travel",
        initial_stage="inquiry",
        stages=TRAVEL_BOOKING_STAGES,
        meta={
            "contact_role_schemas": TRAVEL_CONTACT_ROLE_SCHEMAS,
            # GL account codes (read by the financial listener)
            "revenue_gl_account": "4010",        # Sales Revenue / Travel Commission
            "receivable_gl_account": "1200",     # Accounts Receivable
            "payable_gl_account": "2100",        # Accounts Payable (supplier liability)
            "default_commission_rate": 0.10,     # 10% if no explicit margin exists
        },
    )
    session.add(case_type)
    await session.flush()
    return case_type
