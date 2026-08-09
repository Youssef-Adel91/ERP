"""
app/modules/imports/models/core.py — Import Cycle Domain Models
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

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
    status: ImportStatus = Field(default=ImportStatus.OPEN)
    currency: str = Field(max_length=3, default="EGP")
    fx_rate: Decimal = Field(
        default=Decimal("1.0"), 
        sa_column=Column(Numeric(18, 6), nullable=False)
    )


class ImportExpense(TenantBase, table=True):
    __tablename__ = "import_expenses"
    __table_args__ = ({"schema": "tenant"},)

    dossier_id: UUID = Field(index=True, foreign_key="tenant.import_dossiers.id")
    expense_type: ExpenseType = Field(default=ExpenseType.OTHER)
    amount: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(18, 4), nullable=False))
    vendor_id: UUID | None = Field(default=None, index=True)


class DossierCostLayer(TenantBase, table=True):
    """Linkage between an Import Dossier and Inventory Cost Layers generated during receiving."""
    __tablename__ = "import_dossier_cost_layers"
    __table_args__ = ({"schema": "tenant"},)

    dossier_id: UUID = Field(index=True, foreign_key="tenant.import_dossiers.id")
    layer_id: UUID = Field(index=True, foreign_key="tenant.cost_layers.id")
