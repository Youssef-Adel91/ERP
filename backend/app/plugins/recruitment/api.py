"""
app/plugins/recruitment/api.py — Recruitment Plugin REST API

Exposes:
  - Job Order CRUD
  - Candidate matching endpoints
  - Bulk Excel import
  - Plugin bootstrap (activation) endpoint
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from decimal import Decimal
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.core.security.security import require_role
from app.modules.cases.models.core import Case
from app.modules.contacts.models import Contact
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import UserRole
from app.plugins.recruitment.bootstrap import bootstrap_recruitment_case_type
from app.plugins.recruitment.models.candidate import Candidate
from app.plugins.recruitment.models.job_orders import JobOrder, JobOrderCase, JobOrderStatus
from app.plugins.recruitment.services.matching import (
    attach_candidate_to_job_order,
    find_matching_candidates,
)
from app.plugins.recruitment.services.importing import import_candidates_from_excel
from app.plugins.recruitment.services.pdf_builder import build_offer_letter_pdf

router = APIRouter(prefix="/recruitment", tags=["Recruitment Plugin"])

# RBAC note (Recruitment Readiness Wave): every endpoint below requires an
# authenticated CurrentUser (same baseline pattern as app/plugins/travel).
# Endpoints that cancel a job order or otherwise have irreversible/financial
# impact additionally require OWNER or ADMIN via require_role(...).


# ── Pydantic Schemas ───────────────────────────────────────────────────────────


class JobOrderCreate(BaseModel):
    order_reference: str
    sponsor_id: UUID
    required_profession: str
    target_country: str
    target_count: int
    notes: str | None = None


class JobOrderUpdate(BaseModel):
    required_profession: str | None = None
    target_country: str | None = None
    target_count: int | None = None
    status: JobOrderStatus | None = None
    notes: str | None = None


class AttachCandidateIn(BaseModel):
    case_id: UUID


# ── Plugin Bootstrap ───────────────────────────────────────────────────────────


@router.post("/bootstrap", status_code=status.HTTP_200_OK)
async def activate_plugin(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Idempotent: injects the 'candidate_deployment' CaseType into the core engine
    for this tenant. Safe to call multiple times.
    """
    ct = await bootstrap_recruitment_case_type(session)
    await session.commit()
    return {"message": "Recruitment plugin activated.", "case_type_id": str(ct.id)}


# ── Job Order CRUD ─────────────────────────────────────────────────────────────


@router.post("/job-orders", status_code=status.HTTP_201_CREATED)
async def create_job_order(
    body: JobOrderCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Creates a new job order representing a foreign employer's staffing demand."""
    order = JobOrder(**body.model_dump())
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


@router.get("/job-orders")
async def list_job_orders(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    status: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(JobOrder)
    if status:
        q = q.where(JobOrder.status == status.upper())
    q = q.order_by(JobOrder.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/job-orders/{id}")
async def get_job_order(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    order = await session.get(JobOrder, id)
    if not order:
        raise HTTPException(status_code=404, detail="Job Order not found.")
    return order


@router.patch("/job-orders/{id}")
async def update_job_order(
    id: UUID,
    body: JobOrderUpdate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Edit an open job order (target headcount changed by the sponsor,
    profession/country correction, manual status override, etc).
    target_count cannot be dropped below fulfilled_count — that would make
    the order internally inconsistent with candidates already attached.
    """
    order = await session.get(JobOrder, id)
    if not order:
        raise HTTPException(status_code=404, detail="Job Order not found.")

    data = body.model_dump(exclude_none=True)
    new_target = data.get("target_count")
    if new_target is not None and new_target < order.fulfilled_count:
        raise HTTPException(
            status_code=422,
            detail=(
                f"target_count ({new_target}) cannot be less than "
                f"fulfilled_count ({order.fulfilled_count}) — "
                f"{order.fulfilled_count} candidates are already attached."
            ),
        )
    for field, value in data.items():
        setattr(order, field, value)

    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


@router.delete(
    "/job-orders/{id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def cancel_job_order(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Cancels a job order (soft — sets status=CANCELLED, does not delete the
    row or detach already-matched candidates, since those Cases may still
    be mid-deployment and their history/GL postings must be preserved).
    A FILLED order cannot be cancelled — it already completed its purpose.
    Restricted to OWNER/ADMIN (irreversible, affects an employer-facing
    commitment already in flight).
    """
    order = await session.get(JobOrder, id)
    if not order:
        raise HTTPException(status_code=404, detail="Job Order not found.")
    if order.status == JobOrderStatus.FILLED:
        raise HTTPException(status_code=422, detail="A fully filled job order cannot be cancelled.")

    order.status = JobOrderStatus.CANCELLED
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


# ── Candidate Matching ─────────────────────────────────────────────────────────


@router.get("/job-orders/{id}/candidates/match")
async def match_candidates(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Returns all unassigned candidate Cases whose profession matches
    the job order's required profession.
    """
    candidates = await find_matching_candidates(session, id)
    return {
        "job_order_id": str(id),
        "matched_count": len(candidates),
        "candidates": [
            {
                "case_id": str(c.id),
                "title": c.title,
                "stage": c.current_stage,
                "profession": c.data.get("profession"),
                "nationality": c.data.get("nationality"),
                "passport_number": c.data.get("passport_number"),
            }
            for c in candidates
        ],
    }


@router.post("/job-orders/{id}/candidates", status_code=status.HTTP_201_CREATED)
async def attach_candidate(
    id: UUID,
    body: AttachCandidateIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Attaches a specific candidate Case to a Job Order."""
    link = await attach_candidate_to_job_order(session, id, body.case_id)
    await session.commit()
    return {"message": "Candidate attached successfully.", "link_id": str(link.id)}


@router.get("/job-orders/{id}/candidates")
async def list_job_order_candidates(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Lists all candidates currently attached to a Job Order."""
    result = await session.execute(
        select(JobOrderCase)
        .where(JobOrderCase.job_order_id == id)
        .order_by(JobOrderCase.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    links = result.scalars().all()
    return {"job_order_id": str(id), "candidates": [str(l.case_id) for l in links]}


# ── Bulk Excel Import ─────────────────────────────────────────────────────────


@router.post("/candidates/import")
async def bulk_import_candidates(
    request: Request,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(description="Excel (.xlsx) file of candidate data")],
    job_order_id: UUID | None = None,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Parses an Excel file and bulk-creates candidate Cases.
    Optionally attaches all imported candidates to a specific Job Order.

    Returns a per-row import result with success/failure details.
    """
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Only .xlsx files are accepted.")

    tenant_id: str = request.state.tenant_id
    user_id: str | None = request.state.current_user_id

    file_bytes = await file.read()
    import_result = await import_candidates_from_excel(
        session,
        tenant_id=tenant_id,
        file_bytes=file_bytes,
        created_by=UUID(user_id) if user_id else None,
        job_order_id=job_order_id,
    )
    await session.commit()

    return {
        "summary": {
            "total": import_result.total,
            "created": import_result.created,
            "skipped": import_result.skipped,
            "errors": import_result.errors,
        },
        "rows": [
            {
                "row": r.row,
                "status": r.status,
                "case_id": r.case_id,
                "error": r.error,
            }
            for r in import_result.rows
        ],
    }


# ── Offer Letter PDF ─────────────────────────────────────────────────────────


@router.get("/job-orders/{job_order_id}/candidates/{case_id}/offer-letter")
async def get_offer_letter_pdf(
    job_order_id: UUID,
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Generates and returns a printable A4 job offer letter PDF for a
    candidate attached to a job order.

    Resolves: candidate name/profession (structured Candidate profile if
    one exists, falling back to the Case title/Case.data), sponsor name
    (the JobOrder's sponsor Contact), target country (JobOrder), and salary
    (Candidate.expected_salary if set, else Case.data["salary"]).
    """
    job_order = await session.get(JobOrder, job_order_id)
    if not job_order:
        raise HTTPException(status_code=404, detail="طلب التوظيف غير موجود.")

    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="المرشح غير موجود.")

    # Candidate must actually be attached to this job order.
    link = await session.scalar(
        select(JobOrderCase).where(
            JobOrderCase.job_order_id == job_order_id,
            JobOrderCase.case_id == case_id,
        )
    )
    if not link:
        raise HTTPException(
            status_code=409,
            detail="هذا المرشح غير مرتبط بطلب التوظيف المحدد.",
        )

    candidate = await session.scalar(select(Candidate).where(Candidate.case_id == case_id))
    sponsor = await session.get(Contact, job_order.sponsor_id)

    candidate_name = (candidate.full_name if candidate else None) or case.title or "—"
    profession = (candidate.profession if candidate else None) or job_order.required_profession
    sponsor_name = sponsor.name if sponsor else "—"

    raw_salary = (
        candidate.expected_salary if candidate and candidate.expected_salary is not None
        else (case.data or {}).get("salary")
    )
    salary = Decimal(str(raw_salary)) if raw_salary not in (None, "") else None

    pdf_bytes = build_offer_letter_pdf(
        candidate_name=candidate_name,
        profession=profession,
        sponsor_name=sponsor_name,
        target_country=job_order.target_country,
        salary=salary,
        order_reference=job_order.order_reference,
    )

    filename = f"offer_letter_{str(case_id)[:8]}.pdf"
    import io
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
