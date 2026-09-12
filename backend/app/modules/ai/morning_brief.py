"""
app/modules/ai/morning_brief.py — AI Roadmap Level 3: Automated Morning Brief

Composes today's real numbers (the exact same REPORT_REGISTRY functions
Level 1/Level 2 already use, live-verified against the ledger — see
app.modules.reporting.service) into a short Arabic WhatsApp message.

Reuses app.core.ai.adapter.chat_completion for a natural, friendly
narration pass over that real data — same "AI narrates, never invents"
discipline as app.modules.ai.service.answer_question — but this is a
ONE-WAY push, not a Q&A: there's no user question and no tool-calling step,
because the data to narrate is fixed in advance (financial summary +
this-month-vs-last sales + the top overdue invoices), not chosen by the
model.

Guardrail: an unavailable/misconfigured AI provider must NEVER stop the
brief from going out — a merchant depending on this daily message can't be
silently skipped because a Groq/OpenAI key expired. So this always falls
back to a deterministic, plainly-formatted version of the exact same real
numbers if the narration call fails for any reason. The AI only decides
how the message reads, never what numbers it contains — those come
straight from the reporting layer either way.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.adapter import AIProviderError, AIProviderNotConfigured, chat_completion
from app.modules.reporting.service import (
    get_financial_summary,
    get_overdue_invoices,
    get_sales_this_month_vs_last,
)

logger = logging.getLogger(__name__)

_NARRATION_SYSTEM_PROMPT = (
    "أنت مساعد مالي بترسل ملخص صباحي قصير لتاجر عبر واتساب. هتستلم بيانات "
    "حقيقية بصيغة JSON (إيرادات/مديونيات/مبيعات/فواتير متأخرة). مهمتك فقط "
    "صياغة رسالة واتساب قصيرة وودودة بالعربي تلخص الأرقام دي بوضوح — من "
    "غير أي مقدمات طويلة، ومن غير اختراع أي رقم مش موجود في البيانات "
    "المُعطاة لك. استخدم إيموجي بسيطة مناسبة (📊💰⚠️) وخلي الرسالة قابلة "
    "للقراءة السريعة على الموبايل."
)


def _fallback_text(financial: dict, sales: dict, overdue: dict) -> str:
    """Deterministic formatting used when the AI provider is unavailable or
    the narration call fails — same real numbers, just no LLM narration."""
    lines = [
        "📊 *ملخصك الصباحي*",
        "",
        f"💰 إجمالي الإيرادات: {financial['total_revenue_egp']:.2f} جنيه",
        f"📥 المستحق من العملاء: {financial['total_receivables_egp']:.2f} جنيه",
        f"📤 المستحق للموردين: {financial['total_payables_egp']:.2f} جنيه",
        f"🏦 الرصيد النقدي: {financial['cash_balance_egp']:.2f} جنيه",
        "",
        f"🛒 طلبات هذا الشهر: {sales['orders_this_month']}",
    ]
    if sales.get("orders_trend_pct") is not None:
        lines.append(f"   (تغيّر {sales['orders_trend_pct']:+.1f}% عن الشهر اللي فات)")
    if overdue["count"]:
        lines.append("")
        lines.append(
            f"⚠️ عندك {overdue['count']} فاتورة متأخرة بإجمالي "
            f"{overdue['total_overdue_egp']:.2f} جنيه."
        )
    else:
        lines.append("")
        lines.append("✅ مفيش فواتير متأخرة عليك دلوقتي.")
    return "\n".join(lines)


async def build_morning_brief_text(db: AsyncSession) -> str:
    """
    db must already be tenant-scoped (tenant_session(tenant_id)) — same
    contract as every function in app.modules.reporting.service.
    """
    financial = await get_financial_summary(db)
    sales = await get_sales_this_month_vs_last(db)
    overdue = await get_overdue_invoices(db, limit=5)

    try:
        message = await chat_completion(
            messages=[
                {"role": "system", "content": _NARRATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "بيانات اليوم:\n"
                        f"الملخص المالي: {json.dumps(financial, ensure_ascii=False)}\n"
                        f"المبيعات هذا الشهر مقابل الشهر اللي فات: {json.dumps(sales, ensure_ascii=False)}\n"
                        f"الفواتير المتأخرة: {json.dumps(overdue, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        text = message.get("content")
        if text:
            return text
        logger.info("Morning brief: AI narration returned empty content, using deterministic fallback.")
    except (AIProviderNotConfigured, AIProviderError) as exc:
        logger.info("Morning brief: AI narration unavailable (%s), using deterministic fallback.", exc)

    return _fallback_text(financial, sales, overdue)
