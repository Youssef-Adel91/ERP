"""
app/modules/hr/api/leave_requests.py — Leave Request API Endpoints

Was entirely missing: employees had an ON_LEAVE status but no way to
actually request leave, and no manager approval workflow to put them
into (or out of) that state. This closes that gap.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db as get_db_session
from app.core.security.security import require_role
from app.modules.hr.models.core import Employee, LeaveRequest, LeaveRequestStatus
from app.modules.hr.services.leave import approve_leave_request, reject_leave_request
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import UserRole

router = APIRouter(prefix="/hr/leave-requests", tags=["HR & Payroll"])


class LeaveRequestCreate(BaseModel):
    employee_id: UUID
    start_date: date
    end_date: date
    reason: str | None = None

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: date, info):
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date cannot be before start_date.")
        return v


@router.post("", response_model=LeaveRequest)
async def create_leave_request(
    data: LeaveRequestCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> LeaveRequest:
    """Submits a new PENDING leave request for an employee."""
    employee = await session.get(Employee, data.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    leave_request = LeaveRequest(**data.model_dump(), created_by=current_user.id)
    session.add(leave_request)
    await session.commit()
    await session.refresh(leave_request)
    return leave_request


@router.get("", response_model=list[LeaveRequest])
async def list_leave_requests(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    employee_id: UUID | None = Query(default=None),
    status_filter: LeaveRequestStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[LeaveRequest]:
    """Lists leave requests, optionally filtered by employee or status."""
    q = select(LeaveRequest)
    if employee_id:
        q = q.where(LeaveRequest.employee_id == employee_id)
    if status_filter:
        q = q.where(LeaveRequest.status == status_filter)
    q = q.order_by(LeaveRequest.start_date.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


@router.get("/{id}", response_model=LeaveRequest)
async def get_leave_request(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> LeaveRequest:
    leave_request = await session.get(LeaveRequest, id)
    if not leave_request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return leave_request


@router.post(
    "/{id}/approve",
    response_model=LeaveRequest,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def approve(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> LeaveRequest:
    """
    Approves a PENDING leave request and decrements the employee's leave
    balance accordingly. Restricted to OWNER/ADMIN.
    """
    leave_request = await approve_leave_request(session, id, current_user.id)
    await session.commit()
    await session.refresh(leave_request)
    return leave_request


@router.post(
    "/{id}/reject",
    response_model=LeaveRequest,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def reject(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> LeaveRequest:
    """Rejects a PENDING leave request. Restricted to OWNER/ADMIN."""
    leave_request = await reject_leave_request(session, id, current_user.id)
    await session.commit()
    await session.refresh(leave_request)
    return leave_request
