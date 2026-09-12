"""
app/modules/ai/service.py — AI Bot Core Logic (Copilot Level 1: Grounded Retrieval)

Extracted out of app.modules.ai.router so the exact same grounded-retrieval
logic — live-verified via POST /api/v1/ai/ask (2026-09-11): a real posted
invoice's numbers came back through the bot byte-for-byte matching the
database — can be reused by a second caller: the WhatsApp inbound listener
(app.plugins.whatsapp.listeners.handle_whatsapp_message_ai_bot), so "ask
the bot from WhatsApp" is the same code path as "ask it from the app",
never a second, divergent implementation.

See app.modules.ai.router's module docstring for the full flow
description and the read-only/guardrail discipline this must keep.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.adapter import AIProviderError, AIProviderNotConfigured, chat_completion
from app.core.config import settings
from app.modules.ai.schemas import AskResponse
from app.modules.reporting.service import REPORT_REGISTRY

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "أنت مساعد مالي داخل نظام OmniERP. مهمتك الوحيدة هي الإجابة عن أسئلة "
    "المستخدم عن بيانات شركته الحقيقية باستخدام الأدوات (functions) المتاحة "
    "لك فقط. لا تخترع أي رقم أو اسم عميل أو تاريخ من عندك أبداً — إذا لم تستدعِ "
    "أداة، فلا تذكر أي رقم مطلقاً. إذا كان السؤال يحتاج بيانات ولم تجد أداة "
    "مناسبة، قل بوضوح إن هذا التقرير غير متاح بعد. أجب بإيجاز ووضوح باللغة "
    "التي كتب بها المستخدم سؤاله."
)


def _build_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for name, spec in REPORT_REGISTRY.items()
    ]


async def answer_question(db: AsyncSession, question: str, tenant_id: str | None = None) -> AskResponse:
    """
    db must already be tenant-scoped (get_tenant_db in the HTTP router,
    tenant_session(event.tenant_id) in the WhatsApp listener) — this
    function has no concept of which tenant it's running for beyond
    whatever schema `db` is bound to, exactly like every reporting
    function it calls.

    tenant_id (Phase F, 2026-09-11) is the ONE deliberate exception to
    that rule: REPORT_REGISTRY entries flagged "needs_tenant_id" (today,
    only get_customer_trust_profile) need an explicit tenant_id because
    they cross into the shared PUBLIC-schema Trust Network, where there is
    no tenant-scoped schema to rely on for isolation. Per this project's
    own Lesson #9 (never infer tenant_id magically), both HTTP callers
    (app.modules.ai.router) and the WhatsApp listener must pass it in
    explicitly — it is never guessed here.
    """
    now = datetime.now(UTC)

    try:
        first_message = await chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            tools=_build_tools(),
        )
    except AIProviderNotConfigured as exc:
        return AskResponse(answer=str(exc), report_used=None, data=None, generated_at=now, model=settings.AI_MODEL)
    except AIProviderError as exc:
        return AskResponse(
            answer=f"عذراً، حدث خطأ أثناء التواصل مع البوت: {exc}",
            report_used=None,
            data=None,
            generated_at=now,
            model=settings.AI_MODEL,
        )

    tool_calls = first_message.get("tool_calls") or []

    if not tool_calls:
        return AskResponse(
            answer=first_message.get("content") or "لم أتمكن من فهم السؤال، حاول صياغته بشكل مختلف.",
            report_used=None,
            data=None,
            generated_at=now,
            model=settings.AI_MODEL,
        )

    # Only ever execute the FIRST tool call — one grounded lookup per
    # question (Level 2's multi-report variance analysis is future work).
    call = tool_calls[0]
    fn_name = call["function"]["name"]
    try:
        fn_args = json.loads(call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        fn_args = {}

    spec = REPORT_REGISTRY.get(fn_name)
    if spec is None:
        logger.warning("AI model requested unknown tool: %s", fn_name)
        return AskResponse(
            answer="عذراً، حدث خطأ داخلي أثناء تجهيز الإجابة.",
            report_used=None,
            data=None,
            generated_at=now,
            model=settings.AI_MODEL,
        )

    # Real, tenant-scoped DB call — the ONLY source of numbers in this answer.
    # A report flagged needs_tenant_id (e.g. get_customer_trust_profile,
    # Phase F) additionally needs the explicit tenant_id — never inferred —
    # because it queries the shared public-schema Trust Network.
    if spec.get("needs_tenant_id"):
        if tenant_id is None:
            logger.warning("Tool %s needs tenant_id but none was provided to answer_question", fn_name)
            return AskResponse(
                answer="عذراً، حدث خطأ داخلي أثناء تجهيز الإجابة.",
                report_used=None,
                data=None,
                generated_at=now,
                model=settings.AI_MODEL,
            )
        result_data = await spec["fn"](db, tenant_id=tenant_id, **fn_args)
    else:
        result_data = await spec["fn"](db, **fn_args)

    try:
        final_message = await chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
                {"role": "assistant", "content": None, "tool_calls": [call]},
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result_data, ensure_ascii=False, default=str),
                },
            ],
        )
        answer_text = final_message.get("content") or "تم جلب البيانات، لكن تعذّر صياغة رد نصي."
    except (AIProviderNotConfigured, AIProviderError) as exc:
        logger.warning("AI narration call failed after a successful tool call: %s", exc)
        answer_text = "تعذّر صياغة رد نصي، لكن البيانات الحقيقية مرفقة أدناه."

    return AskResponse(
        answer=answer_text,
        report_used=fn_name,
        data=result_data,
        generated_at=now,
        model=settings.AI_MODEL,
    )
