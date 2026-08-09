"""
app/plugins/recruitment/bootstrap.py — Recruitment Plugin Configuration Injector

DECOUPLING CONTRACT:
  ✅ Imports ONLY from app.core (EventBus, DB) and app.modules.cases (CaseType model)
  ✅ Injects CaseType configuration as DATA rows — never patches core engine code
  ❌ Never alters core engine logic
  ❌ Never imports from app.modules.accounting directly

Usage:
    Called once during tenant provisioning or via the plugin activation endpoint.
    Idempotent — safe to call repeatedly (uses INSERT ... ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models.core import CaseType

# ── Recruitment Stage Definitions ──────────────────────────────────────────────
#
# Each stage defines:
#   id            — machine key used in Case.current_stage and transitions
#   label         — human-readable label (English)
#   label_ar      — human-readable label (Arabic)
#   order         — enforces forward-only movement by default
#   is_terminal   — if true, no further transitions allowed
#   terminal_status — Case.status value to set when this stage is reached
#   allow_rollback — if true, engine allows downward order movement to this stage
#   schema        — JSON Schema for required/optional data fields at this stage

CANDIDATE_DEPLOYMENT_STAGES: list[dict] = [
    {
        "id": "submitted",
        "label": "Application Submitted",
        "label_ar": "تم تقديم الطلب",
        "order": 1,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["passport_number", "profession", "target_country", "nationality"],
            "properties": {
                "passport_number": {"type": "string", "maxLength": 20},
                "passport_expiry": {"type": "string", "format": "date"},
                "profession": {"type": "string", "maxLength": 200},
                "profession_ar": {"type": "string", "maxLength": 200},
                "target_country": {"type": "string", "maxLength": 100},
                "nationality": {"type": "string", "maxLength": 100},
                "date_of_birth": {"type": "string", "format": "date"},
                "years_of_experience": {"type": "integer", "minimum": 0},
            },
        },
    },
    {
        "id": "document_check",
        "label": "Document Verification",
        "label_ar": "التحقق من المستندات",
        "order": 2,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["documents_verified_by"],
            "properties": {
                "documents_verified_by": {"type": "string"},
                "documents_verified_at": {"type": "string", "format": "date-time"},
                "missing_documents": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "notes": {"type": "string"},
            },
        },
    },
    {
        "id": "medical",
        "label": "Medical Examination",
        "label_ar": "الفحص الطبي",
        "order": 3,
        "is_terminal": False,
        "allow_rollback": True,  # Can return to document_check if test fails
        "schema": {
            "type": "object",
            "required": ["medical_center", "result"],
            "properties": {
                "medical_center": {"type": "string", "maxLength": 255},
                "examination_date": {"type": "string", "format": "date"},
                "result": {"type": "string", "enum": ["fit", "unfit", "pending"]},
                "report_reference": {"type": "string", "maxLength": 100},
            },
        },
    },
    {
        "id": "contracted",
        "label": "Contract Signed",
        "label_ar": "تم توقيع العقد",
        "order": 4,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["contract_reference", "salary", "contract_duration_months"],
            "properties": {
                "contract_reference": {"type": "string", "maxLength": 100},
                "salary": {"type": "number", "minimum": 0},
                "currency": {"type": "string", "default": "EGP"},
                "contract_duration_months": {"type": "integer", "minimum": 1},
                "signed_at": {"type": "string", "format": "date"},
                # Financial hook: commission_amount is written by the GL listener
                "commission_amount": {"type": "number"},
                "commission_posted": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "deployed",
        "label": "Deployed / Travelled",
        "label_ar": "تم السفر / النشر",
        "order": 5,
        "is_terminal": False,
        "schema": {
            "type": "object",
            "required": ["travel_date", "flight_reference"],
            "properties": {
                "travel_date": {"type": "string", "format": "date"},
                "flight_reference": {"type": "string", "maxLength": 100},
                "arrival_confirmed": {"type": "boolean", "default": False},
                "deployment_fee_posted": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "closed",
        "label": "Closed / Returned",
        "label_ar": "مغلق / عاد",
        "order": 6,
        "is_terminal": True,
        "terminal_status": "CLOSED",
        "schema": {
            "type": "object",
            "properties": {
                "closure_reason": {"type": "string"},
                "return_date": {"type": "string", "format": "date"},
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
            "properties": {
                "cancellation_reason": {"type": "string"},
                "cancelled_by": {"type": "string"},
            },
        },
    },
]

# ── Sponsor/Employer Role Schema ───────────────────────────────────────────────
#
# Stored in CaseType.meta["contact_role_schemas"]. The engine uses this to
# validate CaseContact.meta payloads when contacts are attached.

CONTACT_ROLE_SCHEMAS: dict[str, dict] = {
    "candidate": {
        "description": "The individual being deployed.",
        "required": ["full_name", "passport_number", "nationality"],
        "properties": {
            "full_name": {"type": "string"},
            "full_name_ar": {"type": "string"},
            "passport_number": {"type": "string"},
            "passport_expiry": {"type": "string", "format": "date"},
            "nationality": {"type": "string"},
            "profession": {"type": "string"},
            "target_country": {"type": "string"},
        },
    },
    "sponsor": {
        "description": "The foreign employer / sponsoring company.",
        "required": ["company_name", "sponsorship_number"],
        "properties": {
            "company_name": {"type": "string"},
            "company_name_ar": {"type": "string"},
            "sponsorship_number": {"type": "string"},
            "sponsor_country": {"type": "string"},
            "contact_person": {"type": "string"},
            "visa_quota": {"type": "integer", "minimum": 0},
        },
    },
    "guarantor": {
        "description": "Local Egyptian guarantor (kafeel).",
        "required": ["national_id"],
        "properties": {
            "national_id": {"type": "string"},
            "guarantee_amount": {"type": "number"},
        },
    },
}


async def bootstrap_recruitment_case_type(session: AsyncSession) -> CaseType:
    """
    Idempotent: inserts the 'candidate_deployment' CaseType if it does not
    already exist. Called once per tenant during plugin activation.

    Returns the existing or newly created CaseType.
    """
    result = await session.execute(
        select(CaseType).where(CaseType.code == "candidate_deployment")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    case_type = CaseType(
        code="candidate_deployment",
        name="Candidate Deployment",
        name_ar="نشر الكوادر / العمالة",
        plugin_key="recruitment",
        initial_stage="submitted",
        stages=CANDIDATE_DEPLOYMENT_STAGES,
        meta={
            "contact_role_schemas": CONTACT_ROLE_SCHEMAS,
            "commission_gl_account": "4010",   # Revenue: Agency Commission
            "commission_rate_default": 0.10,    # 10% of contract salary
            "deployment_fee_gl_account": "4010",
        },
    )
    session.add(case_type)
    await session.flush()
    return case_type
