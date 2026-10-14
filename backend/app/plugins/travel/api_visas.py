"""
app/plugins/travel/api_visas.py — Visa Application Tracking API

See app/plugins/travel/models/visa.py for the full rationale. Endpoints
live under both /travel/visas (global list — "which visas are pending
across all bookings") and /travel/cases/{case_id}/visas (scoped to one
booking), since both views are genuinely useful for an agency.

Changes in this revision (Travel Readiness Wave):
  - Soft delete: DELETE /visas/{visa_id} now sets is_active=False when
    the visa has financial impact (fee_charged>0 or cost>0), and falls
    back to hard delete only for zero-cost draft records.
  - list_visas / list_case_visas: filter is_active=True by default;
    pass ?include_archived=true to see soft-deleted records.
  - RBAC: all write endpoints require CurrentUser; destructive endpoints
    (delete) additionally require OWNER or ADMIN.
  - Document sub-resource: upload / list / download / delete documents
    for a visa application (passport scans, photos, forms).
"""
from __future__ import annotations

import mimetypes
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.core.security.security import require_role
from app.modules.cases.models.core import Case
from app.modules.cases.models.vendor import Vendor
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import UserRole
from app.plugins.travel.models.document import VisaDocument
from app.plugins.travel.models.visa import VISA_STATUS_ORDER, VisaApplication, VisaStatus

router = APIRouter(prefix="/travel", tags=["Travel Plugin — Visas"])

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

_ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ── Pydantic Schemas ────────────────────────────────────────────────────────


class VisaCreateIn(BaseModel):
    passenger_name: str
    passport_number: str | None = None
    destination_country: str
    visa_type: str = "tourist"
    vendor_id: UUID | None = None
    expected_decision_date: date | None = None
    cost: Decimal = Decimal("0")
    fee_charged: Decimal = Decimal("0")
    currency: str = "EGP"
    notes: str | None = None


class VisaPatchIn(BaseModel):
    passenger_name: str | None = None
    passport_number: str | None = None
    destination_country: str | None = None
    visa_type: str | None = None
    vendor_id: UUID | None = None
    submitted_date: date | None = None
    expected_decision_date: date | None = None
    decision_date: date | None = None
    visa_number: str | None = None
    visa_issue_date: date | None = None
    visa_expiry_date: date | None = None
    cost: Decimal | None = None
    fee_charged: Decimal | None = None
    rejection_reason: str | None = None
    notes: str | None = None


class VisaStatusTransitionIn(BaseModel):
    status: VisaStatus
    rejection_reason: str | None = None
    # Set True to allow a status change that looks like backward movement
    # without it being a legitimate resubmission (REJECTED -> DOCUMENTS_COLLECTED
    # is always allowed; anything else out-of-order needs this flag).
    force: bool = False


class VisaOut(BaseModel):
    id: UUID
    case_id: UUID
    passenger_name: str
    passport_number: str | None
    destination_country: str
    visa_type: str
    status: str
    is_active: bool
    vendor_id: UUID | None
    vendor_name: str | None = None
    submitted_date: date | None
    expected_decision_date: date | None
    decision_date: date | None
    visa_number: str | None
    visa_issue_date: date | None
    visa_expiry_date: date | None
    cost: Decimal
    fee_charged: Decimal
    currency: str
    rejection_reason: str | None
    notes: str | None
    booking_title: str | None = None

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id: UUID
    visa_id: UUID
    filename: str
    content_type: str
    file_size_bytes: int
    uploaded_by: UUID | None
    notes: str | None

    class Config:
        from_attributes = True


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _to_out(session: AsyncSession, visa: VisaApplication) -> VisaOut:
    vendor_name = None
    if visa.vendor_id:
        vendor = await session.get(Vendor, visa.vendor_id)
        vendor_name = vendor.name_ar or vendor.name if vendor else None
    case = await session.get(Case, visa.case_id)
    return VisaOut(
        **VisaOut.model_validate(visa).model_dump(exclude={"vendor_name", "booking_title"}),
        vendor_name=vendor_name,
        booking_title=case.title if case else None,
    )


def _has_financial_impact(visa: VisaApplication) -> bool:
    """Return True if this visa has any collected fees or agency costs."""
    return bool(visa.fee_charged and visa.fee_charged > 0) or bool(visa.cost and visa.cost > 0)


# ── Global list ──────────────────────────────────────────────────────────────


@router.get("/visas", response_model=list[VisaOut])
async def list_visas(
    current_user: CurrentUser,
    status_filter: str | None = None,
    destination_country: str | None = None,
    include_archived: bool = Query(default=False, description="Pass true to include soft-deleted records"),
    session: AsyncSession = Depends(get_tenant_db),
):
    """Lists all visa applications across all bookings."""
    q = select(VisaApplication)
    if not include_archived:
        q = q.where(VisaApplication.is_active == True)  # noqa: E712
    if status_filter:
        q = q.where(VisaApplication.status == status_filter)
    if destination_country:
        q = q.where(VisaApplication.destination_country.ilike(f"%{destination_country}%"))
    q = q.order_by(VisaApplication.expected_decision_date.nulls_last())
    result = await session.execute(q)
    visas = result.scalars().all()
    return [await _to_out(session, v) for v in visas]


# ── Scoped to a booking ──────────────────────────────────────────────────────


@router.get("/cases/{case_id}/visas", response_model=list[VisaOut])
async def list_case_visas(
    case_id: UUID,
    current_user: CurrentUser,
    include_archived: bool = Query(default=False),
    session: AsyncSession = Depends(get_tenant_db),
):
    q = select(VisaApplication).where(VisaApplication.case_id == case_id)
    if not include_archived:
        q = q.where(VisaApplication.is_active == True)  # noqa: E712
    result = await session.execute(q)
    visas = result.scalars().all()
    return [await _to_out(session, v) for v in visas]


@router.post("/cases/{case_id}/visas", response_model=VisaOut, status_code=status.HTTP_201_CREATED)
async def create_visa(
    case_id: UUID,
    body: VisaCreateIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="الحجز غير موجود.")
    visa = VisaApplication(case_id=case_id, **body.model_dump())
    session.add(visa)
    await session.commit()
    await session.refresh(visa)
    return await _to_out(session, visa)


@router.patch("/visas/{visa_id}", response_model=VisaOut)
async def update_visa(
    visa_id: UUID,
    body: VisaPatchIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(visa, field, value)
    session.add(visa)
    await session.commit()
    await session.refresh(visa)
    return await _to_out(session, visa)


@router.post("/visas/{visa_id}/transition", response_model=VisaOut)
async def transition_visa_status(
    visa_id: UUID,
    body: VisaStatusTransitionIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Moves a visa application to a new status. Auto-stamps the relevant date
    field (submitted_date on -> SUBMITTED, decision_date on -> APPROVED/
    REJECTED/RECEIVED) so staff don't have to fill dates in manually on top
    of picking the status.
    """
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")

    current_order = VISA_STATUS_ORDER.get(visa.status, 0)
    new_order = VISA_STATUS_ORDER.get(body.status, 0)
    is_resubmission = visa.status == VisaStatus.REJECTED and body.status in (
        VisaStatus.DOCUMENTS_COLLECTED, VisaStatus.SUBMITTED,
    )
    if new_order < current_order and not is_resubmission and not body.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"الانتقال من '{visa.status}' إلى '{body.status}' يبدو رجوعًا للخلف. "
                "لو ده مقصود (مثلاً إعادة تقديم بعد رفض)، ابعت force=true."
            ),
        )

    visa.status = body.status
    if body.status == VisaStatus.SUBMITTED and not visa.submitted_date:
        from datetime import UTC, datetime
        visa.submitted_date = datetime.now(UTC).date()
    if body.status in (VisaStatus.APPROVED, VisaStatus.REJECTED, VisaStatus.RECEIVED) and not visa.decision_date:
        from datetime import UTC, datetime
        visa.decision_date = datetime.now(UTC).date()
    if body.status == VisaStatus.REJECTED and body.rejection_reason:
        visa.rejection_reason = body.rejection_reason

    session.add(visa)
    await session.commit()
    await session.refresh(visa)
    return await _to_out(session, visa)


@router.delete(
    "/visas/{visa_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
)
async def delete_visa(
    visa_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Soft-deletes a visa application if it has financial impact
    (fee_charged > 0 or cost > 0); otherwise hard-deletes it.

    Soft delete (is_active=False) preserves the audit trail for any
    collected fees. Hard delete is only used for zero-cost draft records
    that were created by mistake.
    """
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")

    if _has_financial_impact(visa):
        visa.is_active = False
        session.add(visa)
        await session.commit()
    else:
        await session.delete(visa)
        await session.commit()


# ── Visa Documents ────────────────────────────────────────────────────────────


@router.post(
    "/visas/{visa_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_visa_document(
    visa_id: UUID,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Uploads a document (passport scan, photo, form, etc.) and attaches it
    to the specified visa application.

    Accepted types: PDF, JPEG, PNG, GIF, DOC, DOCX.
    Maximum size: 5 MB per file.
    """
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")

    # -- MIME type validation
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"نوع الملف '{content_type}' غير مدعوم. "
                "الأنواع المقبولة: PDF, JPEG, PNG, GIF, DOC, DOCX."
            ),
        )

    # -- Size validation (read all bytes, check limit)
    data = await file.read()
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"حجم الملف يتجاوز الحد المسموح (5 ميجابايت). الحجم الحالي: {len(data) / 1024 / 1024:.1f} MB.",
        )

    doc = VisaDocument(
        visa_id=visa_id,
        filename=file.filename or "document",
        content_type=content_type,
        file_size_bytes=len(data),
        data=data,
        uploaded_by=current_user.id,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/visas/{visa_id}/documents", response_model=list[DocumentOut])
async def list_visa_documents(
    visa_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Lists all documents attached to a visa application (metadata only, no binary data)."""
    visa = await session.get(VisaApplication, visa_id)
    if not visa:
        raise HTTPException(status_code=404, detail="طلب التأشيرة غير موجود.")
    result = await session.execute(
        select(VisaDocument).where(VisaDocument.visa_id == visa_id)
    )
    docs = result.scalars().all()
    return docs


@router.get("/visas/{visa_id}/documents/{doc_id}")
async def download_visa_document(
    visa_id: UUID,
    doc_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Downloads a specific document as binary content."""
    doc = await session.get(VisaDocument, doc_id)
    if not doc or doc.visa_id != visa_id:
        raise HTTPException(status_code=404, detail="المستند غير موجود.")
    return Response(
        content=doc.data,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.delete(
    "/visas/{visa_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_visa_document(
    visa_id: UUID,
    doc_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Hard-deletes a document attachment. Documents have no financial impact so hard delete is safe."""
    doc = await session.get(VisaDocument, doc_id)
    if not doc or doc.visa_id != visa_id:
        raise HTTPException(status_code=404, detail="المستند غير موجود.")
    await session.delete(doc)
    await session.commit()
