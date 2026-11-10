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
    report_params: dict[str, Any] | None = Field(default=None, description="المعاملات المستخدمة (الفترة...) لإعادة تشغيل/تصدير نفس التقرير")
    table: dict[str, Any] | None = Field(default=None, description="التقرير بصيغة جدول قياسية قابلة للعرض والتنزيل")
    generated_at: datetime
    model: str
    mode: str = Field(default="llm", description="llm = نموذج ذكاء اصطناعي، rules = محرك القواعد (بدون نموذج)")
    suggestions: list[str] = Field(default_factory=list)


# ── Level 4: Agentic Document Drafting ──────────────────────────────────────


class DraftOverdueReminderRequest(BaseModel):
    contact_id: UUID


class SubmitDraftResponse(BaseModel):
    draft: Any  # AIDraftedMessage — Any here to avoid a schemas->models circular import
    approval_request_id: UUID


class RunReportRequest(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ExportReportRequest(RunReportRequest):
    format: str = Field(default="xlsx", pattern="^(xlsx|csv)$")
