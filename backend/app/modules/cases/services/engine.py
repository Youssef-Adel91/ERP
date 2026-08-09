"""
app/modules/cases/services/engine.py — Generic Case Process Engine

Responsibilities:
  1. Stage Transition State Machine — validates allowed moves per CaseType config.
  2. Double-Booking Prevention — uses SELECT ... FOR UPDATE + an overlap query
     to guarantee no two Cases hold the same Resource for overlapping dates.
  3. EventBus Hook — publishes CaseStageTransitionedEvent after every transition
     so vertical plugins can listen and trigger financial postings automatically.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.cases.models.core import (
    Case,
    CaseContact,
    CaseStageHistory,
    CaseType,
    Resource,
)

logger = logging.getLogger(__name__)


# ── Domain Event ───────────────────────────────────────────────────────────────


class CaseStageTransitionedEvent(DomainEvent):
    """
    Published after every successful stage transition.
    Vertical plugins subscribe to "case.stage.transitioned" and check
    payload["case_type_code"] to filter for their own type.
    """

    event_type: str = "case.stage.transitioned"


# ── Internal helpers ───────────────────────────────────────────────────────────


def _get_stage_map(case_type: CaseType) -> dict[str, dict[str, Any]]:
    """Returns {stage_id: stage_dict} from the CaseType stages array."""
    return {s["id"]: s for s in case_type.stages}


def _validate_transition(
    case_type: CaseType, from_stage: str, to_stage: str
) -> dict[str, Any]:
    """
    Validates that a transition from `from_stage` → `to_stage` is permitted.

    Rules (derived from CaseType.stages configuration):
      • `to_stage` must exist in stages.
      • `from_stage` must NOT be terminal.
      • `to_stage` order must be ≥ from_stage order (no backwards movement unless
        stage defines `allow_rollback: true`).

    Returns the destination stage dict.
    Raises HTTPException(422) if the transition is invalid.
    """
    stage_map = _get_stage_map(case_type)

    src = stage_map.get(from_stage)
    dst = stage_map.get(to_stage)

    if not src:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Source stage '{from_stage}' not found in CaseType '{case_type.code}'.",
        )
    if not dst:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Target stage '{to_stage}' is not a valid stage in CaseType '{case_type.code}'.",
        )
    if src.get("is_terminal", False):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stage '{from_stage}' is terminal. No further transitions are allowed.",
        )

    src_order = src.get("order", 0)
    dst_order = dst.get("order", 0)
    allow_rollback = dst.get("allow_rollback", False)

    if dst_order < src_order and not allow_rollback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Backwards transition from '{from_stage}' (order={src_order}) "
                f"to '{to_stage}' (order={dst_order}) is not permitted."
            ),
        )

    return dst


async def _check_resource_availability(
    session: AsyncSession,
    resource_id: UUID,
    start_date: Any,
    end_date: Any,
    exclude_case_id: UUID | None = None,
) -> None:
    """
    Prevents double-booking by checking for date-range overlaps on a Resource.

    Uses SELECT ... FOR UPDATE (row-level lock) on the conflicting rows to
    prevent race conditions under concurrent requests.

    Two date ranges [A_start, A_end] and [B_start, B_end] overlap iff:
        A_start < B_end AND A_end > B_start
    """
    if not resource_id or not start_date or not end_date:
        return

    q = (
        select(Case)
        .where(
            and_(
                Case.resource_id == resource_id,
                Case.status == "ACTIVE",
                Case.start_date < end_date,
                Case.end_date > start_date,
            )
        )
        .with_for_update()
    )
    if exclude_case_id:
        q = q.where(Case.id != exclude_case_id)

    result = await session.execute(q)
    conflicts = result.scalars().all()

    if conflicts:
        conflicting_ids = [str(c.id) for c in conflicts]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Resource {resource_id} is already booked for the requested period. "
                f"Conflicting case(s): {conflicting_ids}"
            ),
        )


# ── Core Public API ────────────────────────────────────────────────────────────


async def create_case(
    session: AsyncSession,
    *,
    tenant_id: str,
    case_type_id: UUID,
    title: str | None = None,
    resource_id: UUID | None = None,
    start_date: Any = None,
    end_date: Any = None,
    data: dict[str, Any] | None = None,
    contacts: list[dict[str, Any]] | None = None,
    created_by: UUID | None = None,
) -> Case:
    """
    Opens a new Case in the initial stage defined by the CaseType.

    Steps:
      1. Resolve and validate CaseType.
      2. Check resource availability (if resource + dates provided).
      3. INSERT Case in initial_stage.
      4. INSERT initial CaseStageHistory row (from_stage=None).
      5. INSERT CaseContact rows.
      6. Flush (no commit — caller owns the transaction boundary).
    """
    # 1. Resolve CaseType
    ct = await session.get(CaseType, case_type_id)
    if not ct:
        raise HTTPException(status_code=404, detail=f"CaseType {case_type_id} not found.")

    # 2. Double-booking check
    if resource_id and start_date and end_date:
        await _check_resource_availability(session, resource_id, start_date, end_date)

    # 3. Create Case
    case = Case(
        case_type_id=case_type_id,
        current_stage=ct.initial_stage,
        status="ACTIVE",
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        data=data or {},
        title=title,
        created_by=created_by,
    )
    session.add(case)
    await session.flush()

    # 4. Initial history record (from_stage=None signals "opened")
    session.add(
        CaseStageHistory(
            case_id=case.id,
            from_stage=None,
            to_stage=ct.initial_stage,
            changed_by=created_by,
            changed_at=datetime.utcnow(),
            reason="Case opened",
            data_snapshot=case.data.copy(),
        )
    )

    # 5. Attach contacts
    for c in contacts or []:
        session.add(
            CaseContact(
                case_id=case.id,
                contact_id=UUID(c["contact_id"]),
                role=c.get("role", "primary"),
                meta=c.get("meta", {}),
            )
        )

    await session.flush()
    return case


async def transition_case(
    session: AsyncSession,
    *,
    tenant_id: str,
    case_id: UUID,
    to_stage: str,
    reason: str | None = None,
    data_patch: dict[str, Any] | None = None,
    changed_by: UUID | None = None,
) -> Case:
    """
    Moves a Case from its current stage to `to_stage`.

    Steps:
      1. Lock the Case row (FOR UPDATE) to prevent concurrent transitions.
      2. Validate the transition via state machine.
      3. Re-check resource availability if dates changed.
      4. Update Case.current_stage and optionally patch Case.data.
      5. If destination stage is terminal, set Case.status accordingly.
      6. INSERT an immutable CaseStageHistory audit row.
      7. Publish CaseStageTransitionedEvent to the EventBus (outbox pattern).
      8. Flush — caller commits.
    """
    # 1. Lock Case row
    result = await session.execute(
        select(Case).where(Case.id == case_id).with_for_update()
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")

    if case.status in ("CLOSED", "CANCELLED"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Case is already {case.status}. No further transitions are possible.",
        )

    # 2. Resolve CaseType and validate transition
    ct = await session.get(CaseType, case.case_type_id)
    if not ct:
        raise HTTPException(status_code=500, detail="CaseType configuration missing.")

    dst_stage_def = _validate_transition(ct, case.current_stage, to_stage)

    # 3. Resource availability re-check (in case dates were patched)
    if case.resource_id and case.start_date and case.end_date:
        await _check_resource_availability(
            session,
            case.resource_id,
            case.start_date,
            case.end_date,
            exclude_case_id=case.id,
        )

    from_stage = case.current_stage

    # 4. Mutate Case
    case.current_stage = to_stage
    if data_patch:
        case.data = {**case.data, **data_patch}

    # 5. Terminal stage handling
    is_terminal = dst_stage_def.get("is_terminal", False)
    if is_terminal:
        terminal_status = dst_stage_def.get("terminal_status", "CLOSED")
        case.status = terminal_status
        # Release resource if booking closes
        if case.resource_id and terminal_status in ("CLOSED", "CANCELLED"):
            resource = await session.get(Resource, case.resource_id)
            if resource:
                resource.status = "AVAILABLE"
                session.add(resource)

    session.add(case)

    # 6. Immutable audit log
    session.add(
        CaseStageHistory(
            case_id=case.id,
            from_stage=from_stage,
            to_stage=to_stage,
            changed_by=changed_by,
            changed_at=datetime.utcnow(),
            reason=reason,
            data_snapshot=case.data.copy(),
        )
    )

    await session.flush()

    # 7. Publish domain event (Transactional Outbox — stays in same transaction)
    event_bus = get_event_bus()
    await event_bus.publish(
        CaseStageTransitionedEvent(
            tenant_id=tenant_id,
            payload={
                "case_id": str(case.id),
                "case_type_code": ct.code,
                "plugin_key": ct.plugin_key,
                "from_stage": from_stage,
                "to_stage": to_stage,
                "is_terminal": is_terminal,
                "resource_id": str(case.resource_id) if case.resource_id else None,
                "changed_by": str(changed_by) if changed_by else None,
                "reason": reason,
            },
        ),
        session=session,
    )

    return case
