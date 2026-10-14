"""
app/plugins/recruitment/api_interviews.py — Interview Scheduling API

Full CRUD for Interview records attached to a candidate Case, plus a
convenience endpoint to record a result (pass/fail/reschedule/no-show)
without a full PATCH payload.

DECOUPLING CONTRACT:
  ✅ FK to Case (candidate) and optionally JobOrder
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case
from app.modules.system.dependencies import CurrentUser
from app.plugins.recruitment.models.interview import Interview, InterviewResult
from app.plugins.recruitment.models.job_orders import JobOrder

router = APIRouter(prefix="/recruitment", tags=["Recruitment Plugin — Interviews"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class InterviewIn(BaseModel):
    scheduled_at: datetime
    job_order_id: UUID | None = None
    interviewer_name: str | None = None
    location: str | None = None
    notes: str | None = None


class InterviewPatchIn(BaseModel):
    scheduled_at: datetime | None = None
    job_order_id: UUID | None = None
    interviewer_name: str | None = None
    location: str | None = None
    result: str | None = None
    notes: str | None = None


class InterviewResultIn(BaseModel):
    result: str
    notes: str | None = None


class InterviewOut(BaseModel):
    id: UUID
    case_id: UUID
    job_order_id: UUID | None
    scheduled_at: datetime
    interviewer_name: str | None
    location: str | None
    result: str
    notes: str | None

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_case_or_404(session: AsyncSession, case_id: UUID) -> Case:
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="المرشح (الحالة) غير موجود.")
    return case


async def _get_interview_or_404(session: AsyncSession, interview_id: UUID, case_id: UUID) -> Interview:
    interview = await session.get(Interview, interview_id)
    if not interview or interview.case_id != case_id:
        raise HTTPException(status_code=404, detail="المقابلة غير موجودة لهذه الحالة.")
    return interview


def _valid_result(value: str) -> str:
    try:
        return InterviewResult(value.upper())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"نتيجة غير صالحة: {value}. القيم المسموحة: "
            + ", ".join(r.value for r in InterviewResult),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/cases/{case_id}/interviews", response_model=list[InterviewOut])
async def list_interviews(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> list[InterviewOut]:
    """Lists all interviews scheduled for a candidate, most recent first."""
    await _get_case_or_404(session, case_id)
    result = await session.execute(
        select(Interview)
        .where(Interview.case_id == case_id)
        .order_by(Interview.scheduled_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/cases/{case_id}/interviews",
    response_model=InterviewOut,
    status_code=status.HTTP_201_CREATED,
)
async def schedule_interview(
    case_id: UUID,
    body: InterviewIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> InterviewOut:
    """Schedules a new interview for a candidate."""
    await _get_case_or_404(session, case_id)
    if body.job_order_id:
        job_order = await session.get(JobOrder, body.job_order_id)
        if not job_order:
            raise HTTPException(status_code=404, detail="طلب التوظيف المحدد غير موجود.")

    interview = Interview(case_id=case_id, **body.model_dump())
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


@router.get("/cases/{case_id}/interviews/{interview_id}", response_model=InterviewOut)
async def get_interview(
    case_id: UUID,
    interview_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> InterviewOut:
    return await _get_interview_or_404(session, interview_id, case_id)


@router.patch("/cases/{case_id}/interviews/{interview_id}", response_model=InterviewOut)
async def update_interview(
    case_id: UUID,
    interview_id: UUID,
    body: InterviewPatchIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> InterviewOut:
    """Updates an interview — reschedule, change interviewer/location, or set a result directly."""
    interview = await _get_interview_or_404(session, interview_id, case_id)
    data = body.model_dump(exclude_unset=True)
    if "result" in data and data["result"] is not None:
        data["result"] = _valid_result(data["result"])
    for field, value in data.items():
        setattr(interview, field, value)
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


@router.post("/cases/{case_id}/interviews/{interview_id}/result", response_model=InterviewOut)
async def record_interview_result(
    case_id: UUID,
    interview_id: UUID,
    body: InterviewResultIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> InterviewOut:
    """Convenience endpoint: records PASSED/FAILED/RESCHEDULED/NO_SHOW for an interview."""
    interview = await _get_interview_or_404(session, interview_id, case_id)
    interview.result = _valid_result(body.result)
    if body.notes is not None:
        interview.notes = body.notes
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return interview


@router.delete(
    "/cases/{case_id}/interviews/{interview_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_interview(
    case_id: UUID,
    interview_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Deletes an interview record entirely (e.g. added by mistake). To record
    an interview that happened but was cancelled/rescheduled, use the
    /result endpoint with RESCHEDULED instead of deleting — that preserves
    the history.
    """
    interview = await _get_interview_or_404(session, interview_id, case_id)
    await session.delete(interview)
    await session.commit()
