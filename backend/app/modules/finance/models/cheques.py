"""
app/modules/finance/models/cheques.py — Cheque Domain Models
"""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Index, Numeric
from sqlmodel import Column, Field

from app.core.db.base import TenantBase


class ChequeType(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class ChequeStatus(StrEnum):
    PENDING = "pending"
    DEPOSITED = "deposited"
    CLEARED = "cleared"
    BOUNCED = "bounced"
    CANCELLED = "cancelled"


class Cheque(TenantBase, table=True):
    __tablename__ = "cheques"
    __table_args__ = (
        Index("ix_cheques_cheque_number", "cheque_number"),
        Index("ix_cheques_due_date", "due_date"),
        Index("ix_cheques_status", "status"),
        Index("ix_cheques_contact_id", "contact_id"),
        {"schema": "tenant"},
    )

    cheque_number: str = Field(max_length=50, index=True)
    amount: Decimal = Field(
        sa_column=Column(Numeric(12, 2), nullable=False)
    )
    issue_date: date = Field(nullable=False)
    due_date: date = Field(nullable=False)
    bank_name: str = Field(max_length=255)
    
    cheque_type: ChequeType = Field(
        sa_column=Column(sa.Enum(ChequeType, name='chequetype', schema='tenant'), nullable=False)
    )
    status: ChequeStatus = Field(
        default=ChequeStatus.PENDING,
        sa_column=Column(sa.Enum(ChequeStatus, name='chequestatus', schema='tenant'), default=ChequeStatus.PENDING, nullable=False)
    )

    contact_id: UUID = Field(foreign_key="tenant.contacts.id")
    invoice_id: UUID | None = Field(default=None) 
    transaction_id: UUID | None = Field(default=None)
