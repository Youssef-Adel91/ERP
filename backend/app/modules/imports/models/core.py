"""
app/modules/imports/models/core.py — Import Cycle Domain Models
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, Date, Numeric
from sqlmodel import Field

from app.core.db.base import TenantBase


class ImportStatus(StrEnum):
    OPEN = "OPEN"
    CUSTOMS = "CUSTOMS"
    CLEARED = "CLEARED"
    CLOSED = "CLOSED"


class ExpenseType(StrEnum):
    FREIGHT = "FREIGHT"
    CUSTOMS = "CUSTOMS"
    CLEARANCE = "CLEARANCE"
    OTHER = "OTHER"


class ImportDossier(TenantBase, table=True):
    __tablename__ = "import_dossiers"
    __table_args__ = ({"schema": "tenant"},)

    dossier_number: str = Field(max_length=100, index=True, unique=True)
    supplier_id: UUID = Field(index=True)
    # Bare sa.Enum(ImportStatus) resolves against the connection's default
    # search_path, not this tenant's schema -- same bug class already fixed
    # for Employee.status/LeaveRequest.status/Payslip.status (see NOTE in
    # app/modules/hr/models/core.py). Fixed live 2026-09-23 -- see
    # z2b3c4d5e6f7_create_import_enum_types_and_expenses_table.py.
    status: ImportStatus = Field(
        default=ImportStatus.OPEN,
        sa_column=Column(
            sa.Enum(ImportStatus, name="importstatus", schema="tenant", create_type=False),
            nullable=False,
        ),
    )
    currency: str = Field(max_length=3, default="EGP")
    fx_rate: Decimal = Field(
        default=Decimal("1.0"), 
        sa_column=Column(Numeric(18, 6), nullable=False)
    )


class ImportExpense(TenantBase, table=True):
    __tablename__ = "import_expenses"
    __table_args__ = ({"schema": "tenant"},)

    dossier_id: UUID = Field(index=True, foreign_key="tenant.import_dossiers.id")
    # See NOTE on ImportDossier.status above -- same fix.
    expense_type: ExpenseType = Field(
        default=ExpenseType.OTHER,
        sa_column=Column(
            sa.Enum(ExpenseType, name="expensetype", schema="tenant", create_type=False),
            nullable=False,
        ),
    )
    amount: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(18, 4), nullable=False))
    vendor_id: UUID | None = Field(default=None, index=True)


class DossierCostLayer(TenantBase, table=True):
    """Linkage between an Import Dossier and Inventory Cost Layers generated during receiving."""
    __tablename__ = "import_dossier_cost_layers"
    __table_args__ = ({"schema": "tenant"},)

    dossier_id: UUID = Field(index=True, foreign_key="tenant.import_dossiers.id")
    layer_id: UUID = Field(index=True, foreign_key="tenant.cost_layers.id")
