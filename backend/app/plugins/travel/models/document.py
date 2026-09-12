"""
app/plugins/travel/models/document.py — Visa Application Document Storage

WHY THIS EXISTS:
Agencies must collect physical documents for each visa application — passport
scans, photos, bank statements, application forms — before submission. Without
a structured attachment store, staff either leave files scattered on a shared
drive (no audit trail) or mark the visa "documents collected" without proof
(risk of submission failure).

This model stores each document as a BYTEA blob inside PostgreSQL. For typical
visa document sizes (passport scan ≤ 1 MB, photos ≤ 2 MB, forms ≤ 2 MB) this
is the pragmatic choice:
  ✅ Zero external dependency (no S3 bucket to provision or lose credentials for)
  ✅ Documents are transactionally consistent with the visa record they belong to
  ✅ Backed up by the same DB backup strategy already in place
  ✅ Easy to migrate to S3-compatible storage later — the API surface
     (upload, list, download, delete) stays identical; only the storage
     backend changes.

Size limits enforced at the API layer (5 MB per file). Supported MIME types:
  application/pdf, image/jpeg, image/png, image/gif,
  application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document

DECOUPLING CONTRACT:
  ✅ FK to VisaApplication (CASCADE DELETE) and optionally a user_id
  ✅ Pure storage — no business logic, no GL posting
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Column, ForeignKey, Index, LargeBinary, Text
from sqlmodel import Field

from app.core.db.base import TenantBase


class VisaDocument(TenantBase, table=True):
    """
    A single document attached to a VisaApplication.
    One visa can have multiple documents (passport, photo, form, ...).
    """
    __tablename__ = "travel_visa_documents"
    __table_args__ = (
        Index("ix_travel_visa_documents_visa", "visa_id"),
        {"schema": "tenant"},
    )

    visa_id: UUID = Field(
        sa_column=Column(
            ForeignKey("tenant.travel_visa_applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    filename: str = Field(max_length=255)
    content_type: str = Field(
        max_length=100,
        description="MIME type e.g. application/pdf, image/jpeg",
    )
    file_size_bytes: int = Field(
        default=0,
        description="File size in bytes — stored for display, validated at upload time",
    )

    # The file content — stored as BYTEA.
    # 5 MB soft cap enforced by the API endpoint; no hard DB constraint so that
    # an admin can override it without a schema change if truly needed.
    data: bytes = Field(
        sa_column=Column(LargeBinary, nullable=False),
        exclude=True,  # never serialized into Pydantic output — callers use the download endpoint
    )

    # Who uploaded it (optional — allows anonymous uploads during bootstrapping)
    uploaded_by: UUID | None = Field(default=None)

    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
