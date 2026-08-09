"""
app/modules/hr/models/core.py — HR & Payroll Domain Models
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

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
    status: EmployeeStatus = Field(default=EmployeeStatus.ACTIVE)


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
