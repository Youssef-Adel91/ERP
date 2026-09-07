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
    
    # NOTE: ChequeType/ChequeStatus member NAMES are uppercase (INCOMING,
    # PENDING, ...) but their VALUES — and the native Postgres enum labels
    # created by c7d8e9f0a1b2_add_cheques_table.py's `tenant.chequetype`/
    # `tenant.chequestatus` types, matching the OpenAPI schema — are
    # lowercase ("incoming", "pending", ...). Every other StrEnum column in
    # this codebase (JournalEntryStatus, AccountType, ShiftStatus, etc.) has
    # member name == member value, so a bare sa.Enum(...) "just works" there
    # by relying on SQLAlchemy's default behavior of binding a Python Enum's
    # `.name`. Cheque is the only column where name != value, which made
    # that default binding send the uppercase `.name` ("INCOMING") to
    # Postgres instead of the lowercase `.value` ("incoming") the DB enum
    # actually contains, causing
    # `InvalidTextRepresentationError: invalid input value for enum
    # tenant.chequetype: "INCOMING"`. values_callable tells SQLAlchemy to
    # bind/validate against each member's `.value` instead of its `.name`,
    # matching the lowercase DB labels (and the lowercase OpenAPI schema)
    # without needing to touch the already-correct DB enum types.
    cheque_type: ChequeType = Field(
        sa_column=Column(
            sa.Enum(
                ChequeType,
                name='chequetype',
                schema='tenant',
                values_callable=lambda enum_cls: [e.value for e in enum_cls],
            ),
            nullable=False,
        )
    )
    status: ChequeStatus = Field(
        default=ChequeStatus.PENDING,
        sa_column=Column(
            sa.Enum(
                ChequeStatus,
                name='chequestatus',
                schema='tenant',
                values_callable=lambda enum_cls: [e.value for e in enum_cls],
            ),
            default=ChequeStatus.PENDING,
            nullable=False,
        )
    )

    contact_id: UUID = Field(foreign_key="tenant.contacts.id")
    invoice_id: UUID | None = Field(default=None) 
    transaction_id: UUID | None = Field(default=None)
