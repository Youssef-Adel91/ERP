"""
app/plugins/recruitment/api_candidates.py — Structured Candidate Profile API

Provides a CRUD "profile" endpoint for the structured Candidate record
attached 1:1 to a candidate Case (case_type "candidate_deployment"). Works
alongside the existing free-form Case.data fields — does NOT replace them
in this revision (see models/candidate.py docstring for the full rationale
and what still reads from Case.data: services/matching.py and
listeners.py's commission calculation are unchanged here).

DECOUPLING CONTRACT:
  ✅ FK to Case (candidate)
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case
from app.modules.system.dependencies import CurrentUser
from app.plugins.recruitment.models.candidate import Candidate, CandidateAvailability

router = APIRouter(prefix="/recruitment", tags=["Recruitment Plugin — Candidates"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class CandidateProfileIn(BaseModel):
    full_name: str
    full_name_ar: str | None = None
    passport_number: str | None = None
    passport_expiry: date | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    gender: str | None = None  # male / female
    profession: str | None = None
    phone: str | None = None
    expected_salary: Decimal | None = None
    availability_status: str = CandidateAvailability.AVAILABLE
    notes: str | None = None


class CandidateProfilePatchIn(BaseModel):
    full_name: str | None = None
    full_name_ar: str | None = None
    passport_number: str | None = None
    passport_expiry: date | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    gender: str | None = None
    profession: str | None = None
    phone: str | None = None
    expected_salary: Decimal | None = None
    availability_status: str | None = None
    notes: str | None = None


class CandidateOut(BaseModel):
    id: UUID
    case_id: UUID
    full_name: str
    full_name_ar: str | None
    passport_number: str | None
    passport_expiry: date | None
    date_of_birth: date | None
    nationality: str | None
    gender: str | None
    profession: str | None
    phone: str | None
    expected_salary: Decimal | None
    availability_status: str
    notes: str | None

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_case_or_404(session: AsyncSession, case_id: UUID) -> Case:
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="المرشح (الحالة) غير موجود.")
    return case


async def _get_candidate_by_case(session: AsyncSession, case_id: UUID) -> Candidate | None:
    result = await session.execute(
        select(Candidate).where(Candidate.case_id == case_id)
    )
    return result.scalar_one_or_none()


# ── Endpoints ─────────────────────────────────────────────────────────────────
# One structured profile per candidate Case (1:1) — GET/PUT/DELETE under
# /recruitment/cases/{case_id}/candidate-profile, mirroring the
# /travel/cases/{case_id}/passengers pattern but singular (1:1 vs 1:many).


@router.get(
    "/cases/{case_id}/candidate-profile",
    response_model=CandidateOut,
)
async def get_candidate_profile(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> CandidateOut:
    """Fetches the structured candidate profile for a candidate Case, if any."""
    await _get_case_or_404(session, case_id)
    candidate = await _get_candidate_by_case(session, case_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="لا يوجد ملف مرشح منظم لهذه الحالة بعد. استخدم PUT لإنشائه.",
        )
    return candidate


@router.put(
    "/cases/{case_id}/candidate-profile",
    response_model=CandidateOut,
)
async def upsert_candidate_profile(
    case_id: UUID,
    body: CandidateProfileIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> CandidateOut:
    """
    Creates or fully replaces the structured candidate profile for a
    candidate Case. Idempotent — PUT is safe to call repeatedly (e.g. a
    staff member re-saving the profile form).
    """
    await _get_case_or_404(session, case_id)
    candidate = await _get_candidate_by_case(session, case_id)
    if candidate:
        for field, value in body.model_dump().items():
            setattr(candidate, field, value)
    else:
        candidate = Candidate(case_id=case_id, **body.model_dump())
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


@router.patch(
    "/cases/{case_id}/candidate-profile",
    response_model=CandidateOut,
)
async def patch_candidate_profile(
    case_id: UUID,
    body: CandidateProfilePatchIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> CandidateOut:
    """Partially updates an existing candidate profile (404 if none exists yet — use PUT to create)."""
    await _get_case_or_404(session, case_id)
    candidate = await _get_candidate_by_case(session, case_id)
    if not candidate:
        raise HTTPException(
            status_code=404,
            detail="لا يوجد ملف مرشح منظم لهذه الحالة بعد. استخدم PUT لإنشائه.",
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


@router.delete(
    "/cases/{case_id}/candidate-profile",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_candidate_profile(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Deletes the structured candidate profile. This never deletes the
    underlying Case — it only removes the structured profile record,
    reverting display to the legacy Case.data fields.
    """
    candidate = await _get_candidate_by_case(session, case_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="لا يوجد ملف مرشح منظم لهذه الحالة.")
    await session.delete(candidate)
    await session.commit()


@router.get(
    "/candidates",
    response_model=list[CandidateOut],
)
async def list_candidate_profiles(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    availability_status: str | None = None,
    profession: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CandidateOut]:
    """
    Lists all structured candidate profiles across the tenant, optionally
    filtered by availability status or profession — useful for a recruiter
    scanning the full candidate pool rather than one job order's matches.
    """
    limit = min(limit, 500)
    offset = max(offset, 0)
    q = select(Candidate)
    if availability_status:
        q = q.where(Candidate.availability_status == availability_status.upper())
    if profession:
        q = q.where(Candidate.profession.ilike(f"%{profession}%"))
    q = q.order_by(Candidate.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())
