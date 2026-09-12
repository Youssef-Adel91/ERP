"""
app/core/ai/adapter.py — OpenAI-Compatible LLM Adapter

This is the ONLY place in the codebase that talks HTTP to an AI provider.
Deliberately built on plain httpx (already a project dependency) against
the OpenAI Chat Completions wire format, rather than the `openai` Python
SDK, because that wire format is what Groq, OpenAI, and most self-hosted
inference servers (vLLM, Ollama's OpenAI-compat mode) all speak — so the
provider is an env-var change (AI_BASE_URL / AI_API_KEY / AI_MODEL in
app.core.config.Settings), never a code change. This directly implements
the "adapter, not a subsystem" principle from the internal Phase 8 AI
blueprint (OmniERP_Blueprints_Phase0_Phase8.pdf, §I.0): the model is
commodity infrastructure, swappable at will; nothing about the ERP's own
logic should ever depend on which vendor is behind this call.

Current default (see config.py): Groq's free OpenAI-compatible endpoint,
because that's what's actually configured for this tenant today. Moving
to OpenAI later is: set AI_BASE_URL=https://api.openai.com/v1, AI_MODEL to
a real OpenAI model name, AI_API_KEY to an OpenAI key. Nothing else changes.

Safety note (Phase 8 blueprint §I.8, guardrail #1): this adapter is used
ONLY for read-only grounded retrieval today (app.modules.ai.router calls
it to pick + narrate typed reporting functions). It has no concept of
writing to the ledger and never will — any future agentic/drafting use of
this adapter must route its output through the existing approval engine
(app.modules.approvals) exactly like a human-created document, never
committing anything directly.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIProviderNotConfigured(Exception):
    """Raised when AI_API_KEY isn't set. Callers turn this into a clear,
    non-crashing user-facing message — same discipline as
    app.core.notifications.email's SMTP-not-configured no-op and
    app.modules.billing.services.gateway's Paymob-not-configured refusal."""


class AIProviderError(Exception):
    """Raised when the provider is configured but the HTTP call itself
    fails (network error, non-2xx response, malformed body)."""


async def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """
    Call the configured provider's /chat/completions endpoint and return
    the raw `choices[0].message` dict (may contain `content` and/or
    `tool_calls`, per the OpenAI wire format).

    Low default temperature deliberately: this adapter backs a financial
    reporting bot, not a creative-writing tool — answers should be the
    same every time for the same underlying data.
    """
    if not settings.AI_API_KEY:
        raise AIProviderNotConfigured(
            "لم يتم إعداد مزود الذكاء الاصطناعي بعد (AI_API_KEY غير مضبوط). "
            "أضف المفتاح في متغيرات البيئة (.env) لتفعيل البوت."
        )

    payload: dict[str, Any] = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    url = f"{settings.AI_BASE_URL.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.AI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        logger.error("AI provider request failed (network): %s", exc)
        raise AIProviderError(f"تعذّر الاتصال بمزود الذكاء الاصطناعي: {exc}") from exc

    if resp.status_code >= 400:
        logger.error(
            "AI provider returned an error: status=%s body=%s",
            resp.status_code,
            resp.text[:2000],
        )
        raise AIProviderError(
            f"مزود الذكاء الاصطناعي أرجع خطأ ({resp.status_code}). "
            "راجع سجلات الخادم للتفاصيل."
        )

    try:
        data = resp.json()
        return data["choices"][0]["message"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.error("AI provider returned an unexpected response shape: %s", resp.text[:2000])
        raise AIProviderError("رد مزود الذكاء الاصطناعي بصيغة غير متوقعة.") from exc
