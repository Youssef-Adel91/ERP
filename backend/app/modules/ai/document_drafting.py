"""
app/modules/ai/document_drafting.py — AI Roadmap Level 4: Agentic Document
Drafting (Overdue Payment Reminder slice)

draft_overdue_payment_reminder(db, contact_id) grounds itself in the exact
same real data discipline as every other Copilot level: it queries the
contact's own overdue POSTED sales invoices directly from sales_invoices
(same status=POSTED + due_date < today filter used by
app.modules.reporting.service.get_overdue_invoices and by
app.modules.sales.services.reminders.process_overdue_reminders — never a
second, potentially-diverging definition of "overdue"), asks the AI to
narrate a polite Arabic WhatsApp reminder from those real numbers (with a
deterministic fallback if the AI provider is unavailable, same discipline
as app.modules.ai.morning_brief.build_morning_brief_text), and persists the
result as an app.modules.ai.models.AIDraftedMessage row in DRAFT state.

Nothing is sent to the customer here. Sending only happens after a real
human APPROVE decision recorded through the existing Approval Engine — see
app.modules.approvals.api.decide and
app.plugins.whatsapp.listeners.handle_ai_draft_approved.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.adapter import AIProviderError, AIProviderNotConfigured, chat_completion
from app.modules.ai.models import AIDraftChannel, AIDraftedMessage, AIDraftPurpose
from app.modules.contacts.models import Contact
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "أنت مساعد يكتب رسائل واتساب مهذبة لتذكير العملاء بفواتير متأخرة السداد. "
    "استخدم فقط الأرقام والبيانات المذكورة في رسالة المستخدم — لا تخترع أي "
    "رقم فاتورة أو مبلغ أو تاريخ من عندك أبداً. اكتب رسالة قصيرة ومهذبة "
    "باللغة العربية، بدون تهديد أو أسلوب فظ، تذكّر العميل بإجمالي المستحق "
    "وعدد الفواتير المتأخرة وتطلب منه التواصل لترتيب السداد."
)


class NoOverdueInvoicesError(Exception):
    """Raised when the contact has no overdue POSTED invoices — there is
    nothing real to ground a reminder in, so no draft is created rather
    than fabricating one."""


def _fallback_text(contact_name: str, invoices: list[dict]) -> str:
    total = round(sum(i["grand_total_egp"] for i in invoices), 2)
    lines = [
        f"مرحبًا {contact_name}،",
        "",
        f"نود تذكيركم بوجود {len(invoices)} فاتورة/فواتير متأخرة السداد "
        f"بإجمالي {total} جنيه:",
    ]
    for inv in invoices:
        lines.append(
            f"- فاتورة {inv['invoice_number']} بقيمة {inv['grand_total_egp']} جنيه "
            f"(متأخرة {inv['days_overdue']} يوم)"
        )
    lines.append("")
    lines.append("برجاء التواصل معنا في أقرب وقت لترتيب السداد. شكرًا لتعاونكم.")
    return "\n".join(lines)


async def _load_overdue_invoices(db: AsyncSession, contact_id: UUID) -> list[dict]:
    """Same real filter as get_overdue_invoices — status=POSTED and
    due_date < today — scoped to one contact."""
    today = date.today()
    result = await db.execute(
        select(SalesInvoice)
        .where(
            SalesInvoice.contact_id == contact_id,
            SalesInvoice.status == SalesInvoiceStatus.POSTED,
            SalesInvoice.due_date < today,
        )
        .order_by(SalesInvoice.due_date.asc())
    )
    invoices = result.scalars().all()
    return [
        {
            "invoice_number": inv.invoice_number,
            "due_date": inv.due_date.isoformat(),
            "days_overdue": (today - inv.due_date).days,
            "grand_total_egp": float(inv.grand_total),
            "currency": inv.currency,
        }
        for inv in invoices
    ]


async def draft_overdue_payment_reminder(db: AsyncSession, contact_id: UUID) -> AIDraftedMessage:
    """
    db must already be tenant-scoped, exactly like every other Copilot
    level's reporting/service calls. Returns a persisted AIDraftedMessage
    in DRAFT state, not yet flushed to the caller's discretion — caller is
    responsible for session.commit() (kept explicit so the router can
    decide the transaction boundary, same convention as
    approvals/api.py's endpoints).
    """
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise ValueError(f"Contact {contact_id} not found.")

    overdue = await _load_overdue_invoices(db, contact_id)
    if not overdue:
        raise NoOverdueInvoicesError(
            f"Contact {contact_id} has no overdue POSTED invoices — nothing to draft."
        )

    contact_name = contact.name or contact.name_ar or "العميل"
    total = round(sum(i["grand_total_egp"] for i in overdue), 2)

    grounding_data = {
        "contact_id": str(contact_id),
        "contact_name": contact_name,
        "overdue_invoices": overdue,
        "total_overdue_egp": total,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    user_prompt = (
        f"اسم العميل: {contact_name}\n"
        f"عدد الفواتير المتأخرة: {len(overdue)}\n"
        f"إجمالي المستحق: {total} جنيه\n"
        f"تفاصيل الفواتير: {overdue}"
    )

    try:
        message = await chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        draft_text = message.get("content") or ""
        if not draft_text.strip():
            draft_text = _fallback_text(contact_name, overdue)
    except (AIProviderNotConfigured, AIProviderError) as exc:
        logger.warning("AI drafting failed, using deterministic fallback: %s", exc)
        draft_text = _fallback_text(contact_name, overdue)

    draft = AIDraftedMessage(
        purpose=AIDraftPurpose.OVERDUE_PAYMENT_REMINDER,
        channel=AIDraftChannel.WHATSAPP,
        contact_id=contact_id,
        draft_text=draft_text,
        grounding_data=grounding_data,
        created_by=None,
    )
    db.add(draft)
    await db.flush()
    await db.refresh(draft)
    return draft
