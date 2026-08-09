"""
app/plugins/recruitment/services/matching.py — Candidate Matching Service

Queries available Cases (candidate_deployment type, in early stages) whose
profession matches a JobOrder's required_profession, then associates them.

DECOUPLING CONTRACT:
  ✅ Reads from app.modules.cases.models (CaseType, Case) — pure query, no mutation
  ✅ Writes to recruitment-owned models only (JobOrder, JobOrderCase)
  ✅ Triggers stage progression via the core engine's transition_case() function
  ❌ Never writes directly to core accounting tables
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models.core import Case, CaseType
from app.plugins.recruitment.models.job_orders import JobOrder, JobOrderCase, JobOrderStatus

logger = logging.getLogger(__name__)

# Stages where a candidate is still placeable into a job order
_PLACEABLE_STAGES = ("submitted", "document_check", "medical")


async def find_matching_candidates(
    session: AsyncSession,
    job_order_id: UUID,
) -> list[Case]:
    """
    Returns all unassigned candidate Cases matching the JobOrder's
    required_profession that are still in a placeable stage.
    """
    job_order = await session.get(JobOrder, job_order_id)
    if not job_order:
        raise HTTPException(status_code=404, detail="JobOrder not found.")

    # Subquery: case IDs already assigned to ANY job order
    assigned_case_ids_q = select(JobOrderCase.case_id)

    # Resolve the recruitment CaseType to get its id
    ct_result = await session.execute(
        select(CaseType).where(CaseType.code == "candidate_deployment")
    )
    ct = ct_result.scalar_one_or_none()
    if not ct:
        raise HTTPException(
            status_code=500,
            detail="'candidate_deployment' CaseType not found. Run bootstrap first.",
        )

    # Query: active, placeable, unassigned, profession-matching candidates
    result = await session.execute(
        select(Case).where(
            and_(
                Case.case_type_id == ct.id,
                Case.status == "ACTIVE",
                Case.current_stage.in_(_PLACEABLE_STAGES),
                Case.id.not_in(assigned_case_ids_q),
                # JSON path filter on Case.data["profession"]
                # PostgreSQL ->> operator via text; stored as JSONB
                func.lower(Case.data["profession"].as_string()).contains(
                    func.lower(job_order.required_profession)
                ),
            )
        )
    )
    return result.scalars().all()


async def attach_candidate_to_job_order(
    session: AsyncSession,
    job_order_id: UUID,
    case_id: UUID,
) -> JobOrderCase:
    """
    Associates a single candidate Case with a JobOrder.

    Guards:
      - JobOrder must not be FILLED / CANCELLED / EXPIRED.
      - Case must not already be attached to any JobOrder.
      - Increments JobOrder.fulfilled_count; updates status to PARTIALLY_FILLED or FILLED.
    """
    job_order = await session.get(JobOrder, job_order_id)
    if not job_order:
        raise HTTPException(status_code=404, detail="JobOrder not found.")

    if job_order.status in (JobOrderStatus.FILLED, JobOrderStatus.CANCELLED, JobOrderStatus.EXPIRED):
        raise HTTPException(
            status_code=409,
            detail=f"JobOrder is {job_order.status}. Cannot attach more candidates.",
        )

    # Check candidate is not already assigned
    existing = await session.scalar(
        select(JobOrderCase).where(JobOrderCase.case_id == case_id)
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Case {case_id} is already assigned to JobOrder {existing.job_order_id}.",
        )

    link = JobOrderCase(job_order_id=job_order_id, case_id=case_id)
    session.add(link)

    # Update fulfilled counter and status
    job_order.fulfilled_count += 1
    if job_order.fulfilled_count >= job_order.target_count:
        job_order.status = JobOrderStatus.FILLED
    else:
        job_order.status = JobOrderStatus.PARTIALLY_FILLED
    session.add(job_order)

    await session.flush()
    return link
