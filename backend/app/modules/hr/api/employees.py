"""
app/modules/hr/api/employees.py — Employee CRUD API Endpoints

Was entirely missing: payslips.py requires an `employee_id` to generate a
payslip, but there was no way to create or list employees via the API.
This closes that gap so the HR module is actually usable end-to-end.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db as get_db_session
from app.modules.hr.models.core import Employee, EmployeeStatus
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/hr/employees", tags=["HR & Payroll"])


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    national_id: str
    base_salary: Decimal
    hire_date: date
    status: EmployeeStatus = EmployeeStatus.ACTIVE


@router.post("", response_model=Employee)
async def create_employee(
    data: EmployeeCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Employee:
    """Creates a new employee record."""
    employee = Employee(**data.model_dump(), created_by=current_user.id)
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


@router.get("", response_model=list[Employee])
async def list_employees(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
    status_filter: EmployeeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Employee]:
    """Lists all employees, optionally filtered by status."""
    q = select(Employee)
    if status_filter:
        q = q.where(Employee.status == status_filter)
    q = q.order_by(Employee.first_name).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


@router.get("/{id}", response_model=Employee)
async def get_employee(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Employee:
    employee = await session.get(Employee, id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


class EmployeeUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    national_id: str | None = None
    base_salary: Decimal | None = None
    status: EmployeeStatus | None = None


@router.patch("/{id}", response_model=Employee)
async def update_employee(
    id: UUID,
    data: EmployeeUpdate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db_session),
) -> Employee:
    """
    Edit an employee's details, or change status (e.g. to TERMINATED / ON_LEAVE).
    Was previously entirely missing — an employee could be created but never
    updated or let go through the API once entered.
    """
    employee = await session.get(Employee, id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    updates = data.model_dump(exclude_none=True)
    if "base_salary" in updates and updates["base_salary"] < 0:
        raise HTTPException(status_code=422, detail="base_salary cannot be negative.")
    for field, value in updates.items():
        setattr(employee, field, value)

    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee
