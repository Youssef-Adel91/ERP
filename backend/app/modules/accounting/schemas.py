"""
app/modules/accounting/schemas.py — Accounting Module Pydantic Schemas
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.accounting.models import AccountType, JournalEntryStatus


# ── Account ───────────────────────────────────────────────────────────────────


class AccountCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20, description="e.g. '1200'")
    name: str = Field(min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    account_type: AccountType
    is_system: bool = False


class AccountResponse(BaseModel):
    id: UUID
    code: str
    name: str
    name_ar: str | None
    account_type: AccountType
    is_active: bool
    is_system: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountBalanceResponse(BaseModel):
    account_code: str
    account_name: str
    account_type: AccountType
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal  # Positive = normal balance for the account type


# ── Transaction Lines ─────────────────────────────────────────────────────────


class TransactionLineCreateRequest(BaseModel):
    account_code: str = Field(min_length=1, max_length=20)
    debit: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    credit: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_debit_xor_credit(self) -> "TransactionLineCreateRequest":
        d = self.debit
        c = self.credit
        if d > 0 and c > 0:
            raise ValueError("A transaction line cannot have both debit and credit > 0.")
        if d == 0 and c == 0:
            raise ValueError("A transaction line must have a non-zero debit or credit.")
        return self


class TransactionLineResponse(BaseModel):
    id: UUID
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    description: str | None

    model_config = {"from_attributes": True}


# ── Journal Entry ─────────────────────────────────────────────────────────────


class JournalEntryCreateRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    lines: list[TransactionLineCreateRequest] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_balanced(self) -> "JournalEntryCreateRequest":
        total_debit = sum(l.debit for l in self.lines)
        total_credit = sum(l.credit for l in self.lines)
        if total_debit.quantize(Decimal("0.0001")) != total_credit.quantize(Decimal("0.0001")):
            raise ValueError(
                f"Journal entry is unbalanced: "
                f"Σ debits={total_debit} ≠ Σ credits={total_credit}. "
                f"Difference: {abs(total_debit - total_credit)}"
            )
        return self


class JournalEntryResponse(BaseModel):
    id: UUID
    reference: str
    description: str
    status: JournalEntryStatus
    source_type: str | None
    source_id: UUID | None
    created_at: datetime
    posted_at: datetime | None
    lines: list[TransactionLineResponse]

    model_config = {"from_attributes": True}
