"""
app/modules/hr/models/core.py — HR & Payroll Domain Models
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, Date, Numeric
from sqlmodel import Field

from app.core.db.base import TenantBase


class EmployeeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    TERMINATED = "TERMINATED"


class PayslipStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    PAID = "PAID"


class LeaveRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Employee(TenantBase, table=True):
    __tablename__ = "hr_employees"
    __table_args__ = ({"schema": "tenant"},)

    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    national_id: str = Field(max_length=50, unique=True, index=True)
    base_salary: Decimal = Field(
        default=Decimal("0.0"),
        sa_column=Column(Numeric(18, 4), nullable=False)
    )
    hire_date: date = Field(sa_column=Column(Date, nullable=False))
    # NOTE: must be explicitly schema-qualified via sa.Enum(..., schema="tenant"),
    # matching JournalEntryStatus/AccountType/ShiftStatus/etc. elsewhere in the
    # codebase. A bare `sa.Enum(EmployeeStatus)` here casts parameters as
    # unqualified `$N::employeestatus`, which does not resolve since the type
    # only exists inside each tenant schema (created by
    # 99f91dd227cd_add_missing_tenant_models.py). create_type=False because
    # the enum type is already created by that migration.
    status: EmployeeStatus = Field(
        default=EmployeeStatus.ACTIVE,
        sa_column=Column(
            sa.Enum(EmployeeStatus, name="employeestatus", schema="tenant", create_type=False),
            nullable=False,
        ),
    )
    # Remaining paid-leave entitlement, in whole days. Decremented when a
    # LeaveRequest for this employee is approved, restored if an approved
    # request is later reversed. See app/modules/hr/services/leave.py.
    leave_balance_days: int = Field(default=21)


class LeaveRequest(TenantBase, table=True):
    __tablename__ = "hr_leave_requests"
    __table_args__ = ({"schema": "tenant"},)

    employee_id: UUID = Field(index=True, foreign_key="tenant.hr_employees.id")
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date = Field(sa_column=Column(Date, nullable=False))
    reason: str | None = Field(default=None, max_length=500)
    # See NOTE on Employee.status above — same missing-schema bug. Enum type
    # "leaverequeststatus" is created inside the tenant schema by
    # m3h8i9j0k1l2_add_hr_leave_requests.py.
    status: LeaveRequestStatus = Field(
        default=LeaveRequestStatus.PENDING,
        sa_column=Column(
            sa.Enum(LeaveRequestStatus, name="leaverequeststatus", schema="tenant", create_type=False),
            nullable=False,
        ),
    )
    # Set when an OWNER/ADMIN approves or rejects the request.
    decided_by: UUID | None = Field(default=None)
    decided_at: date | None = Field(default=None, sa_column=Column(Date, nullable=True))


class Payslip(TenantBase, table=True):
    __tablename__ = "hr_payslips"
    __table_args__ = ({"schema": "tenant"},)

    employee_id: UUID = Field(index=True, foreign_key="tenant.hr_employees.id")
    period_start: date = Field(sa_column=Column(Date, nullable=False))
    period_end: date = Field(sa_column=Column(Date, nullable=False))
    
    basic_wage: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(18, 4), nullable=False))
    allowances: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(18, 4), nullable=False))
    deductions: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(18, 4), nullable=False))
    net_pay: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(18, 4), nullable=False))
    
    status: PayslipStatus = Field(default=PayslipStatus.DRAFT)
