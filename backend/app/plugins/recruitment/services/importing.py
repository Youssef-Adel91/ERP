"""
app/plugins/recruitment/services/importing.py — Bulk Candidate Excel Importer

Parses an Excel workbook of candidate data and maps each row to a POST /cases
request via the core engine's create_case() function.

DECOUPLING CONTRACT:
  ✅ Calls app.modules.cases.services.engine.create_case() — the public API
  ✅ Does NOT write directly to any DB table except through the engine
  ❌ Never imports from accounting or HR modules

Required Excel columns (case-insensitive):
    full_name | full_name_ar | passport_number | passport_expiry |
    profession | profession_ar | target_country | nationality |
    date_of_birth | years_of_experience | case_type_id (optional)

Returns a structured ImportResult for the API layer to return to the caller.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models.core import CaseType
from app.modules.cases.services.engine import create_case

logger = logging.getLogger(__name__)

# Column aliases → normalised field names
_COL_ALIASES: dict[str, str] = {
    "full name": "full_name",
    "الاسم الكامل": "full_name",
    "name": "full_name",
    "full name (arabic)": "full_name_ar",
    "passport no": "passport_number",
    "passport number": "passport_number",
    "رقم الجواز": "passport_number",
    "passport expiry": "passport_expiry",
    "تاريخ انتهاء الجواز": "passport_expiry",
    "profession": "profession",
    "المهنة": "profession",
    "profession (arabic)": "profession_ar",
    "target country": "target_country",
    "دولة العمل": "target_country",
    "nationality": "nationality",
    "الجنسية": "nationality",
    "date of birth": "date_of_birth",
    "تاريخ الميلاد": "date_of_birth",
    "experience (years)": "years_of_experience",
    "سنوات الخبرة": "years_of_experience",
}

_REQUIRED_FIELDS = {"full_name", "passport_number", "profession", "target_country", "nationality"}


@dataclass
class ImportRowResult:
    row: int
    status: str          # "created" | "skipped" | "error"
    case_id: str | None = None
    error: str | None = None


@dataclass
class ImportResult:
    total: int = 0
    created: int = 0
    skipped: int = 0
    errors: int = 0
    rows: list[ImportRowResult] = field(default_factory=list)


def _normalise_headers(raw_headers: list[str]) -> dict[int, str]:
    """Maps Excel column indices to normalised field names."""
    mapping: dict[int, str] = {}
    for idx, h in enumerate(raw_headers):
        normalised = _COL_ALIASES.get(h.strip().lower())
        if normalised:
            mapping[idx] = normalised
    return mapping


def _row_to_dict(row_values: list[Any], col_map: dict[int, str]) -> dict[str, Any]:
    """Converts a row of raw cell values to a normalised field dict."""
    return {col_map[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row_values) if i in col_map}


async def import_candidates_from_excel(
    session: AsyncSession,
    *,
    tenant_id: str,
    file_bytes: bytes,
    created_by: UUID | None = None,
    job_order_id: UUID | None = None,
) -> ImportResult:
    """
    Parses an .xlsx byte stream and creates candidate Cases via the core engine.

    Each row produces:
      - A Case in "submitted" stage with candidate data in Case.data
      - An optional attachment to a JobOrder if job_order_id is provided

    Args:
        file_bytes   : Raw bytes of the uploaded Excel file.
        tenant_id    : Tenant context for the engine call.
        created_by   : User UUID who triggered the import.
        job_order_id : Optional — attaches created cases to this JobOrder.

    Returns:
        ImportResult with per-row success/failure details.
    """
    try:
        import openpyxl  # type: ignore
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl is required for Excel import. Run: pip install openpyxl",
        )

    result = ImportResult()

    # Resolve the candidate_deployment CaseType
    ct_result = await session.execute(
        select(CaseType).where(CaseType.code == "candidate_deployment")
    )
    ct = ct_result.scalar_one_or_none()
    if not ct:
        raise HTTPException(
            status_code=500,
            detail="'candidate_deployment' CaseType not found. Run bootstrap first.",
        )

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return result

    # First row = headers
    headers = [str(c) if c is not None else "" for c in rows[0]]
    col_map = _normalise_headers(headers)

    missing_required = _REQUIRED_FIELDS - set(col_map.values())
    if missing_required:
        raise HTTPException(
            status_code=422,
            detail=f"Excel is missing required columns: {missing_required}. "
                   f"Found: {set(col_map.values())}",
        )

    for row_idx, raw_row in enumerate(rows[1:], start=2):
        result.total += 1
        row_result = ImportRowResult(row=row_idx, status="error")

        try:
            data = _row_to_dict(list(raw_row), col_map)

            # Skip entirely empty rows
            if not any(data.values()):
                row_result.status = "skipped"
                result.skipped += 1
                result.rows.append(row_result)
                continue

            # Validate minimum required fields
            missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
            if missing:
                row_result.error = f"Missing required fields: {missing}"
                result.errors += 1
                result.rows.append(row_result)
                continue

            # Convert years_of_experience to int if present
            if "years_of_experience" in data:
                try:
                    data["years_of_experience"] = int(float(data["years_of_experience"]))
                except (ValueError, TypeError):
                    data["years_of_experience"] = 0

            # Create the Case via the core engine (single source of truth)
            case = await create_case(
                session,
                tenant_id=tenant_id,
                case_type_id=ct.id,
                title=f"{data.get('full_name', '')} — {data.get('profession', '')}",
                data=data,
                created_by=created_by,
            )

            # Optionally attach to JobOrder
            if job_order_id:
                from app.plugins.recruitment.services.matching import attach_candidate_to_job_order
                try:
                    await attach_candidate_to_job_order(session, job_order_id, case.id)
                except HTTPException:
                    # JobOrder might be full; continue creating case but log warning
                    logger.warning("Could not attach case %s to job order %s (order may be full)", case.id, job_order_id)

            row_result.status = "created"
            row_result.case_id = str(case.id)
            result.created += 1

        except Exception as exc:
            logger.exception("Error importing row %d", row_idx)
            row_result.error = str(exc)
            result.errors += 1

        result.rows.append(row_result)

    return result
