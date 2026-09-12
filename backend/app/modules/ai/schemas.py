"""app/modules/ai/schemas.py — AI Bot Request/Response Contracts"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="سؤال المستخدم بالعربية أو الإنجليزية")


class AskResponse(BaseModel):
    answer: str
    report_used: str | None = Field(
        default=None,
        description="اسم دالة التقرير التي استند إليها الرد (drill-through). "
        "None يعني أن السؤال لم يحتَج بيانات (مثل تحية عابرة).",
    )
    data: dict[str, Any] | None = Field(
        default=None, description="البيانات الحقيقية الراجعة من دالة التقرير — نفس الأرقام المذكورة في الرد."
    )
    generated_at: datetime
    model: str


# ── Level 4: Agentic Document Drafting ──────────────────────────────────────


class DraftOverdueReminderRequest(BaseModel):
    contact_id: UUID


class SubmitDraftResponse(BaseModel):
    draft: Any  # AIDraftedMessage — Any here to avoid a schemas->models circular import
    approval_request_id: UUID
