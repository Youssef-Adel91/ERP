"""
app/modules/hr/services/leave.py — Leave Request Approval Engine

Mirrors the row-locking / status-guard pattern used by
app/modules/hr/services/payroll.py::approve_payslip for the same reasons:
approve/reject is a one-way transition that must not race or double-apply.
"""
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models.core import Employee, LeaveRequest, LeaveRequestStatus


def _leave_days(request: LeaveRequest) -> int:
    """Inclusive day count between start_date and end_date."""
    return (request.end_date - request.start_date).days + 1


async def approve_leave_request(
    session: AsyncSession, leave_request_id: UUID, approver_id: UUID
) -> LeaveRequest:
    """
    Approves a PENDING leave request and decrements the employee's leave
    balance. Locks both rows to prevent a double-approval or a concurrent
    request from over-drawing the balance.
    """
    result = await session.execute(
        select(LeaveRequest).where(LeaveRequest.id == leave_request_id).with_for_update()
    )
    leave_request = result.scalar_one_or_none()
    if not leave_request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave_request.status != LeaveRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only PENDING leave requests can be approved")

    employee_result = await session.execute(
        select(Employee).where(Employee.id == leave_request.employee_id).with_for_update()
    )
    employee = employee_result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    days = _leave_days(leave_request)
    if days > employee.leave_balance_days:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requested {days} day(s) exceed the employee's remaining "
                f"leave balance of {employee.leave_balance_days} day(s)."
            ),
        )

    employee.leave_balance_days -= days
    leave_request.status = LeaveRequestStatus.APPROVED
    leave_request.decided_by = approver_id
    leave_request.decided_at = date.today()

    session.add(employee)
    session.add(leave_request)
    return leave_request


async def reject_leave_request(
    session: AsyncSession, leave_request_id: UUID, approver_id: UUID
) -> LeaveRequest:
    """Rejects a PENDING leave request. No balance change occurs."""
    result = await session.execute(
        select(LeaveRequest).where(LeaveRequest.id == leave_request_id).with_for_update()
    )
    leave_request = result.scalar_one_or_none()
    if not leave_request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if leave_request.status != LeaveRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only PENDING leave requests can be rejected")

    leave_request.status = LeaveRequestStatus.REJECTED
    leave_request.decided_by = approver_id
    leave_request.decided_at = date.today()

    session.add(leave_request)
    return leave_request
