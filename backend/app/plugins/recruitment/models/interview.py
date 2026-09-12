"""
app/plugins/recruitment/models/interview.py — Interview Scheduling

WHY THIS EXISTS:
There was no concept of an "interview" anywhere in the recruitment plugin —
a real recruitment agency's core workflow (schedule a candidate for
interview, record who interviewed them, record pass/fail/reschedule) had
no model, no endpoint, no UI. This closes that gap (P0 per
VERTICAL_SYSTEMS_ROADMAP.md §4 Recruitment).

DECOUPLING CONTRACT:
  ✅ Imports only from app.core.db.base (TenantBase)
  ❌ Never imports from accounting, contacts, or cases core modules directly
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Index
from sqlmodel import Field

from app.core.db.base import TenantBase


class InterviewResult(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    RESCHEDULED = "RESCHEDULED"
    NO_SHOW = "NO_SHOW"


class Interview(TenantBase, table=True):
    """
    A single scheduled interview for a candidate Case. A candidate can have
    multiple Interview rows over time (e.g. rescheduled, or a second-round
    interview) — this is intentionally many-per-Case, not 1:1.
    """

    __tablename__ = "recruitment_interviews"
    __table_args__ = (
        Index("ix_recruitment_interviews_case", "case_id"),
        Index("ix_recruitment_interviews_result", "result"),
        Index("ix_recruitment_interviews_scheduled_at", "scheduled_at"),
        {"schema": "tenant"},
    )

    case_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tenant.cases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    # Optional link to the job order this interview is for — a candidate
    # can be interviewed with a specific employer/job order in mind.
    job_order_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("tenant.recruitment_job_orders.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    scheduled_at: datetime = Field()
    interviewer_name: str | None = Field(default=None, max_length=255)
    location: str | None = Field(
        default=None, max_length=255,
        description="Physical location, or a video-call link/text.",
    )
    result: str = Field(default=InterviewResult.PENDING, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
