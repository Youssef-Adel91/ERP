"""
app/plugins/recruitment/models/candidate.py — Structured Candidate Records

WHY THIS EXISTS:
Candidate identity/travel-document data (profession, nationality, passport
number, salary) previously lived ONLY as free-form JSON in Case.data — no
validation, no dedicated CRUD, no typed fields. That is a real risk for a
commercial deployment handling passport numbers and salary figures. This
model adds a proper structured, validated record per candidate.

DESIGN — additive, not a replacement (same pattern as
app/plugins/travel/models/passenger.py relative to the JSONB passenger
manifest):
  ✅ One Candidate row per candidate Case (1:1 — case_id is UNIQUE).
  ✅ Works ALONGSIDE Case.data — does NOT replace it. The existing matching
     service (services/matching.py) and the financial GL-posting listener
     (listeners.py, which reads case.data["salary"]) are UNCHANGED in this
     revision to avoid risking the just-fixed commission-posting flow.
     Candidate.expected_salary is informational/staff-facing for now; a
     follow-up pass can migrate matching.py to query this table directly
     once the structured data has been live-verified.
  ✅ FK to Case (candidate) — CASCADE DELETE when the Case is removed.
  ❌ Never imports from app.modules.accounting

DECOUPLING CONTRACT (same as every other plugin model in this codebase):
  ✅ Imports only from app.core.db.base (TenantBase)
  ❌ Never imports from accounting, contacts, or cases core modules directly
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Index, Numeric, UniqueConstraint
from sqlmodel import Field

from app.core.db.base import TenantBase


class CandidateAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    MATCHED = "MATCHED"
    DEPLOYED = "DEPLOYED"
    UNAVAILABLE = "UNAVAILABLE"


class Candidate(TenantBase, table=True):
    """
    Structured profile for a single candidate — one row per candidate
    Case (case_type "candidate_deployment"). case_id is UNIQUE: this is a
    1:1 extension of the Case, not a many-to-one join.
    """

    __tablename__ = "recruitment_candidates"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_recruitment_candidates_case"),
        Index("ix_recruitment_candidates_profession", "profession"),
        Index("ix_recruitment_candidates_availability", "availability_status"),
        {"schema": "tenant"},
    )

    case_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tenant.cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Identity
    full_name: str = Field(max_length=255)
    full_name_ar: str | None = Field(default=None, max_length=255)

    # Travel document
    passport_number: str | None = Field(default=None, max_length=50)
    passport_expiry: date | None = Field(default=None)

    # Demographic
    date_of_birth: date | None = Field(default=None)
    nationality: str | None = Field(default=None, max_length=100)
    gender: str | None = Field(default=None, max_length=10)  # male / female

    # Professional
    profession: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    expected_salary: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 4), nullable=True),
    )

    availability_status: str = Field(default=CandidateAvailability.AVAILABLE, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
