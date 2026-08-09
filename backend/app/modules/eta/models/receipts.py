"""
app.modules.eta.models.receipts — ETA e-Receipt (B2C) Domain Models (Phase 5 - Step 5)

Defines:
  1. EtaReceiptBatch: Represents a batch of B2C e-Receipts submitted as a whole (FR-570).
  2. EtaReceipt: B2C receipt record tracking 72-hour offline windows, late-on-arrival flags (FR-574),
     previous_uuid chaining, and local QR verification (F-5, FR-576).
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field

from app.core.db.base import TenantBase


class EtaReceiptState(StrEnum):
    DRAFT = "DRAFT"
    BATCHED = "BATCHED"
    SIGNED = "SIGNED"
    SUBMITTED = "SUBMITTED"
    SUBMIT_UNCERTAIN = "SUBMIT_UNCERTAIN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EtaReceiptBatchState(StrEnum):
    DRAFT = "DRAFT"
    SIGNED = "SIGNED"
    SUBMITTED = "SUBMITTED"
    SUBMIT_UNCERTAIN = "SUBMIT_UNCERTAIN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class EtaReceiptBatch(TenantBase, table=True):
    """
    ETA e-Receipt batch submission container (§5.1, FR-570).
    Unlike B2B invoices, e-Receipts are serialized and signed as a batch.
    """
    __tablename__ = "eta_receipt_batches"
    __table_args__ = ({"schema": "tenant"},)

    tenant_id: UUID = Field(index=True)
    pos_terminal_id: str = Field(max_length=100, index=True)
    receipt_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    receipt_count: int = Field(default=0)
    batch_canonical_hash: str | None = Field(default=None, max_length=64)
    signature_b64: str | None = Field(default=None)
    submission_uuid: str | None = Field(default=None, max_length=100, index=True)
    state: EtaReceiptBatchState = Field(
        default=EtaReceiptBatchState.DRAFT,
        sa_column=Column(sa.String(30), nullable=False, default=EtaReceiptBatchState.DRAFT, index=True),
    )
    submitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class EtaReceipt(TenantBase, table=True):
    """
    Individual B2C e-Receipt tracking record (FR-570, FR-574).
    Tracks POS issuance timestamp, 72-hour offline window, previous_uuid for chaining,
    late-on-arrival auditing, and local QR code payload (F-5).
    """
    __tablename__ = "eta_receipts"
    __table_args__ = ({"schema": "tenant"},)

    tenant_id: UUID = Field(index=True)
    batch_id: UUID | None = Field(default=None, index=True)
    internal_doc_id: str = Field(max_length=100, index=True)
    receipt_number: str = Field(max_length=100, index=True)
    uuid: str | None = Field(default=None, max_length=100, index=True)
    previous_uuid: str | None = Field(default=None, max_length=100)
    state: EtaReceiptState = Field(
        default=EtaReceiptState.DRAFT,
        sa_column=Column(sa.String(30), nullable=False, default=EtaReceiptState.DRAFT, index=True),
    )
    date_time_issued: datetime = Field(sa_type=DateTime(timezone=True))
    late_on_arrival: bool = Field(default=False)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    qr_payload: str | None = Field(default=None)
    public_url: str | None = Field(default=None, max_length=255)
