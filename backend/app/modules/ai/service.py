"""
app/modules/ai/service.py — AI assistant core (grounded retrieval + rule-based fallback)

Two engines, ONE report layer:

  * LLM engine  — when AI_API_KEY is configured: the model picks report(s) from
    REPORT_REGISTRY via function-calling and narrates the real numbers it gets
    back. It never sees a report the caller's role may not open.
  * Rules engine — when no model is configured (or the provider is down): the
    deterministic Arabic/English router in app.modules.reporting.catalog picks
    the report and the answer is built from the report's own summary. So the
    assistant is fully usable — including table + Excel/CSV download — before
    any model is connected; connecting one only upgrades understanding/wording.

Every answer carries `table` (standard shape, renderable + downloadable) and
`report_params` so the UI can export exactly what was asked.

Read-only by construction; see app.core.ai.adapter for why that must stay true.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.adapter import AIProviderError, AIProviderNotConfigured, chat_completion
from app.core.config import settings
from app.modules.ai.schemas import AskResponse
from app.modules.reporting.catalog import (
    can_run,
    fallback_answer,
    route_question,
    suggestions,
)
from app.modules.reporting.service import REPORT_REGISTRY
from app.modules.reporting.tabular import normalize

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "أنت مساعد مالي ذكي داخل نظام Trust Core (المرجع الرقمي للتاجر المصري). مهمتك الإجابة "
    "عن أسئلة المستخدم عن بيانات شركته الحقيقية باستخدام الأدوات (functions) المتاحة لك فقط. "
    "لا تخترع أي رقم أو اسم أو تاريخ من عندك أبداً — إذا لم تستدعِ أداة فلا تذكر أي رقم. "
    "حوّل التعبيرات الزمنية (الشهر ده، الشهر اللي فات، آخر 30 يوم، السنة...) إلى date_from/date_to "
    "بصيغة YYYY-MM-DD اعتماداً على تاريخ اليوم. إذا لم تجد أداة مناسبة قل بوضوح إن هذا التقرير "
    "غير متاح. أجب بإيجاز ووضوح بنفس لغة المستخدم، وأشر إلى أن التقرير يمكن تنزيله Excel."
)

_MAX_TOOL_CALLS = 3


def _build_tools(roles: list[str] | None) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": name, "description": spec["description"], "parameters": spec["parameters"]},
        }
        for name, spec in REPORT_REGISTRY.items()
        if can_run(name, roles)
    ]


async def run_report(db: AsyncSession, name: str, params: dict | None, tenant_id: str | None) -> dict:
    """Execute one registry report (already authorised by the caller)."""
    spec = REPORT_REGISTRY[name]
    args = {k: v for k, v in (params or {}).items() if k in spec["parameters"]["properties"] and v not in (None, "")}
    if spec.get("needs_tenant_id"):
        if tenant_id is None:
            raise ValueError(f"{name} needs tenant_id")
        return await spec["fn"](db, tenant_id=tenant_id, **args)
    return await spec["fn"](db, **args)


def _resp(answer: str, now: datetime, mode: str, report: str | None = None, params: dict | None = None, data=None, table=None) -> AskResponse:
    return AskResponse(
        answer=answer,
        report_used=report,
        report_params=params or None,
        data=data,
        table=table,
        generated_at=now,
        model=settings.AI_MODEL if mode == "llm" else "rules-engine",
        mode=mode,
        suggestions=[] if report else suggestions()[:4],
    )


async def _rules_answer(db, question, tenant_id, roles, now, reason: str | None = None) -> AskResponse:
    routed = route_question(question, roles)
    if routed is None:
        hint = "ما قدرتش أحدد التقرير المطلوب من سؤالك. جرّب سؤال من الأمثلة دي أو افتح كتالوج التقارير."
        return _resp(f"{reason + chr(10) if reason else ''}{hint}", now, "rules")
    name, params = routed
    result = await run_report(db, name, params, tenant_id)
    table = normalize(name, result)
    return _resp(fallback_answer(table), now, "rules", name, params, result, table)


async def answer_question(
    db: AsyncSession, question: str, tenant_id: str | None = None, roles: list[str] | None = None
) -> AskResponse:
    """
    db must already be tenant-scoped. tenant_id is passed explicitly only for
    reports that cross into the shared public schema (Trust Network).
    roles=None means a trusted internal caller (owner's WhatsApp); HTTP callers
    must pass the JWT roles so the assistant can't read what the user can't.
    """
    now = datetime.now(UTC)
    today = date.today().isoformat()
    system = f"{_SYSTEM_PROMPT}\nتاريخ اليوم: {today}."

    try:
        first = await chat_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": question}],
            tools=_build_tools(roles),
        )
    except AIProviderNotConfigured:
        return await _rules_answer(db, question, tenant_id, roles, now)
    except AIProviderError as exc:
        logger.warning("AI provider failed, falling back to rules engine: %s", exc)
        return await _rules_answer(db, question, tenant_id, roles, now)

    tool_calls = first.get("tool_calls") or []
    if not tool_calls:
        # The model chose not to call a tool. If our router can answer it with a real
        # report, prefer that over an unsupported free-text answer.
        routed = route_question(question, roles)
        if routed:
            return await _rules_answer(db, question, tenant_id, roles, now)
        return _resp(first.get("content") or "لم أتمكن من فهم السؤال، حاول صياغته بشكل مختلف.", now, "llm")

    executed: list[tuple[dict, str, dict, dict]] = []
    for call in tool_calls[:_MAX_TOOL_CALLS]:
        fn_name = call["function"]["name"]
        try:
            fn_args = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            fn_args = {}
        if fn_name not in REPORT_REGISTRY:
            logger.warning("AI model requested unknown tool: %s", fn_name)
            continue
        if not can_run(fn_name, roles):
            logger.warning("AI model requested %s which role(s) %s may not run", fn_name, roles)
            continue
        try:
            result = await run_report(db, fn_name, fn_args, tenant_id)
        except Exception:  # a bad argument from the model must not crash the answer
            logger.exception("report %s failed with args %s", fn_name, fn_args)
            continue
        executed.append((call, fn_name, fn_args, result))

    if not executed:
        return await _rules_answer(db, question, tenant_id, roles, now, "ما عندكش صلاحية على التقرير ده أو حصل خطأ في تجهيزه." if roles is not None else None)

    _, fn_name, fn_args, result_data = executed[0]
    table = normalize(fn_name, result_data)

    try:
        final = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
                {"role": "assistant", "content": None, "tool_calls": [c for c, _, _, _ in executed]},
                *[
                    {"role": "tool", "tool_call_id": c["id"], "content": json.dumps(r, ensure_ascii=False, default=str)}
                    for c, _, _, r in executed
                ],
            ],
        )
        answer_text = final.get("content") or fallback_answer(table)
    except (AIProviderNotConfigured, AIProviderError) as exc:
        logger.warning("AI narration failed after a successful tool call: %s", exc)
        answer_text = fallback_answer(table)

    return _resp(answer_text, now, "llm", fn_name, fn_args, result_data, table)
