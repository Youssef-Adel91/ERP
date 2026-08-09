"""
app.modules.eta.services.translation — ETA Rejection Translation & Event Consumer (Phase 5 - Step 4)

Implements:
  1. ETA_ERROR_DICTIONARY: Error translation dictionary mapping ETA codes to Arabic strings
     with actionable deep links (FR-560).
  2. translate_eta_validation_errors: Helper to convert raw ETA JSON errors to Arabic actionable diagnostics.
  3. process_document_status_event: Event consumer for eta.document_status_received.
     Transitions EtaDocument to ACCEPTED or REJECTED. On REJECTED, populates translated_errors
     and returns internal ERP SalesInvoice to DRAFT state for fixing (FR-562).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db.context import current_session
from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.eta.models.core import (
    EtaDocument,
    EtaDocumentState,
    EtaSubmission,
)
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus

# ── ETA Error Code Arabic Translation Dictionary (FR-560) ────────────────────────
ETA_ERROR_DICTIONARY: dict[str, dict[str, str]] = {
    "4049": {
        "title_ar": "كود الصنف غير مسجل أو غير فعال (EGS/GS1)",
        "action_ar": "اضغط هنا لإضافة كود GS1 الصنف ناقص أو تفعيل الكود في سجل الأكواد",
        "deep_link": "/app/eta/codes",
    },
    "4010": {
        "title_ar": "شهادة التوقيع الإلكتروني منتهية الصلاحية أو ملغاة",
        "action_ar": "اضغط هنا لتحديث شهادة التوقيع الإلكتروني أو التحقق من اتصال الـ HSM",
        "deep_link": "/app/eta/settings/signing",
    },
    "4001": {
        "title_ar": "خطأ في التنسيق الرياضي أو هيكل الملف الـ JSON",
        "action_ar": "اضغط هنا لمراجعة الحسابات الرياضية للفاتورة ومطابقة الإجمالي مع البنود",
        "deep_link": "/app/sales/invoices",
    },
    "4031": {
        "title_ar": "الرقم الضريبي للمشتري غير صحيح أو غير مسجل بمصلحة الضرائب",
        "action_ar": "اضغط هنا لتعديل بطاقة العميل وإدخال الرقم الضريبي الصحيح المكون من 9 أرقام",
        "deep_link": "/app/contacts/customers",
    },
    "4071": {
        "title_ar": "تاريخ إصدار الفاتورة يتجاوز الحد المسموح للإرسال (تأخير الإرسال)",
        "action_ar": "اضغط هنا لتقديم طلب استثناء أو مراجعة تاريخ إصدار الفاتورة",
        "deep_link": "/app/eta/submissions",
    },
    "4002": {
        "title_ar": "رقم المستند الداخلي (Internal ID) مكرر في الفواتير السابقة",
        "action_ar": "اضغط هنا لتعديل رقم الفاتورة أو التأكد من عدم إرسال الفاتورة مرتين",
        "deep_link": "/app/sales/invoices",
    },
}


def translate_eta_error(error_code: str, error_message: str | None = None) -> dict[str, str]:
    """
    Translate a single ETA error code to an Arabic description with an actionable deep link (FR-560).
    """
    code_str = str(error_code).strip()
    info = ETA_ERROR_DICTIONARY.get(
        code_str,
        {
            "title_ar": f"خطأ غير معروف من مصلحة الضرائب (رمز: {code_str})",
            "action_ar": error_message or "اضغط هنا لمراجعة تفاصيل المستند والتواصل مع الدعم الفني",
            "deep_link": "/app/eta/submissions",
        },
    )
    return {
        "error_code": code_str,
        "title_ar": info["title_ar"],
        "action_ar": info["action_ar"],
        "deep_link": info["deep_link"],
        "raw_message": error_message or "",
    }


def translate_eta_validation_errors(validation_results: Any) -> list[dict[str, str]]:
    """
    Extract and translate all validation step errors from an ETA callback/response payload.
    """
    translated: list[dict[str, str]] = []

    if not validation_results:
        return translated

    steps = []
    if isinstance(validation_results, dict):
        steps = validation_results.get("validationSteps", [])
        if not steps and "error" in validation_results:
            err = validation_results["error"]
            code = str(err.get("errorCode", "UNKNOWN"))
            msg = err.get("errorMessage", "")
            translated.append(translate_eta_error(code, msg))
            return translated
    elif isinstance(validation_results, list):
        steps = validation_results

    for step in steps:
        if isinstance(step, dict) and step.get("status", "").lower() == "invalid":
            err = step.get("error", {})
            if isinstance(err, dict):
                code = str(err.get("errorCode", step.get("name", "UNKNOWN")))
                msg = err.get("errorMessage", step.get("errorDescription", ""))
                translated.append(translate_eta_error(code, msg))
            elif isinstance(err, str):
                translated.append(translate_eta_error(str(step.get("name", "UNKNOWN")), err))

    return translated


async def process_document_status_event(
    session: AsyncSession,
    tenant_id: UUID,
    event_payload: dict[str, Any],
) -> EtaDocument | None:
    """
    Consumer for 'eta.document_status_received' domain event (FR-560, FR-562).

    1. Locates the EtaDocument by internalId or UUID.
    2. If Accepted:
       - Transitions state to ACCEPTED.
       - Records UUID, long_id, public_url, accepted_at timestamp.
    3. If Rejected:
       - Transitions state to REJECTED.
       - Translates ETA rejection codes to Arabic actionable strings (FR-560).
       - Returns the internal ERP SalesInvoice to DRAFT state for fixing (FR-562).
    """
    internal_id = event_payload.get("internalId")
    doc_uuid = event_payload.get("uuid")
    submission_id = event_payload.get("submissionId")

    if not internal_id and not doc_uuid:
        return None

    # Lookup EtaDocument
    stmt = select(EtaDocument).where(EtaDocument.tenant_id == tenant_id)
    if internal_id:
        stmt = stmt.where(EtaDocument.internal_doc_id == str(internal_id))
    elif doc_uuid:
        stmt = stmt.where(EtaDocument.uuid == str(doc_uuid))

    res = await session.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        return None

    status_str = str(event_payload.get("status", "")).lower()

    if status_str in ("valid", "accepted"):
        doc.state = EtaDocumentState.ACCEPTED
        doc.uuid = event_payload.get("uuid", doc.uuid)
        doc.long_id = event_payload.get("longId", doc.long_id)
        doc.public_url = event_payload.get("publicUrl", doc.public_url)
        doc.accepted_at = datetime.now(UTC)

        # Update parent submission counts if present
        if submission_id or doc.submission_uuid:
            sub_id = submission_id or doc.submission_uuid
            stmt_sub = (
                select(EtaSubmission)
                .where(EtaSubmission.tenant_id == tenant_id)
                .where(EtaSubmission.submission_uuid == sub_id)
            )
            res_sub = await session.execute(stmt_sub)
            sub = res_sub.scalar_one_or_none()
            if sub:
                sub.accepted_count += 1
                session.add(sub)

    elif status_str in ("invalid", "rejected"):
        doc.state = EtaDocumentState.REJECTED
        doc.uuid = event_payload.get("uuid", doc.uuid)
        doc.rejected_at = datetime.now(UTC)

        val_results = event_payload.get("validationResults", {})
        doc.validation_errors = val_results
        doc.translated_errors = translate_eta_validation_errors(val_results)

        # FR-562: Return internal ERP SalesInvoice to DRAFT state for fixing
        stmt_inv = (
            select(SalesInvoice)
            .where(SalesInvoice.invoice_number == doc.internal_doc_id)
        )
        res_inv = await session.execute(stmt_inv)
        invoice = res_inv.scalar_one_or_none()
        if invoice and invoice.status != SalesInvoiceStatus.DRAFT:
            invoice.status = SalesInvoiceStatus.DRAFT
            session.add(invoice)

        # Update parent submission counts if present
        if submission_id or doc.submission_uuid:
            sub_id = submission_id or doc.submission_uuid
            stmt_sub = (
                select(EtaSubmission)
                .where(EtaSubmission.tenant_id == tenant_id)
                .where(EtaSubmission.submission_uuid == sub_id)
            )
            res_sub = await session.execute(stmt_sub)
            sub = res_sub.scalar_one_or_none()
            if sub:
                sub.rejected_count += 1
                session.add(sub)

    session.add(doc)
    await session.commit()
    return doc


async def eta_document_status_received_handler(event: DomainEvent) -> None:
    """
    EventBus handler for 'eta.document_status_received' (FR-560, FR-562).
    """
    session = current_session.get()
    if not session:
        return
    try:
        tenant_uuid = UUID(event.tenant_id)
    except ValueError:
        return

    await process_document_status_event(session, tenant_uuid, event.payload)


def register_eta_event_consumers() -> None:
    """
    Register ETA document status event handlers with the global EventBus.
    """
    bus = get_event_bus()
    bus.subscribe("eta.document_status_received")(eta_document_status_received_handler)
