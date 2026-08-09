"""
app.modules.eta.models.core — Core ETA Compliance Domain Models (Phase 5 - Step 2)

Defines:
  1. EtaTenantConfig: per-tenant ETA configuration, storing credentials by reference in Vault (never plain DB).
  2. EtaDocument: document submission queue and state machine (FR-501, FR-530).
  3. EtaSubmission: batch submission tracker (FR-535).
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


class EtaEnvironment(StrEnum):
    PREPRODUCTION = "PREPRODUCTION"
    PRODUCTION = "PRODUCTION"


class EtaSigningProvider(StrEnum):
    CLOUD_HSM = "CLOUD_HSM"
    LOCAL_AGENT = "LOCAL_AGENT"


class EtaPreflightState(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    READY = "READY"


class EtaDocumentState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    QUEUED = "QUEUED"
    SIGNING = "SIGNING"
    SIGNED = "SIGNED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    SUBMIT_FAILED = "SUBMIT_FAILED"
    RATE_DEFERRED = "RATE_DEFERRED"
    SUBMIT_UNCERTAIN = "SUBMIT_UNCERTAIN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INVALID = "INVALID"
    CANCELLED = "CANCELLED"


class EtaTenantConfig(TenantBase, table=True):
    """
    Per-tenant ETA configuration (FR-510, FR-511).
    Secrets (client_secret) are stored by reference in Vault, never in Postgres.
    """
    __tablename__ = "eta_tenant_configs"
    __table_args__ = ({"schema": "tenant"},)

    tenant_id: UUID = Field(index=True, unique=True)
    environment: EtaEnvironment = Field(
        default=EtaEnvironment.PREPRODUCTION,
        sa_column=Column(sa.String(20), nullable=False, default=EtaEnvironment.PREPRODUCTION),
    )
    client_id: str = Field(max_length=255)
    client_secret_ref: str | None = Field(default=None, max_length=255)
    taxpayer_rin: str = Field(max_length=50, index=True)
    activity_code: str = Field(max_length=50)
    branch_eta_codes: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    signing_provider: EtaSigningProvider = Field(
        default=EtaSigningProvider.CLOUD_HSM,
        sa_column=Column(sa.String(30), nullable=False, default=EtaSigningProvider.CLOUD_HSM),
    )
    preflight_state: EtaPreflightState = Field(
        default=EtaPreflightState.UNVERIFIED,
        sa_column=Column(sa.String(30), nullable=False, default=EtaPreflightState.UNVERIFIED),
    )
    is_live: bool = Field(default=False)
    went_live_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class EtaDocument(TenantBase, table=True):
    """
    ETA Document tracking queue and state machine (§4.1, FR-501).
    """
    __tablename__ = "eta_documents"
    __table_args__ = ({"schema": "tenant"},)

    tenant_id: UUID = Field(index=True)
    internal_doc_type: str = Field(max_length=50, index=True)  # sales_invoice | credit_note | debit_note
    internal_doc_id: str = Field(max_length=100, index=True)  # taxpayer-side document ID
    eta_document_type: str = Field(max_length=1, index=True)  # I | C | D
    eta_document_type_version: str = Field(default="1.0", max_length=10)
    uuid: str | None = Field(default=None, max_length=100, index=True)  # ETA-assigned UUID on acceptance
    long_id: str | None = Field(default=None, max_length=100)  # Public verification ID
    submission_uuid: str | None = Field(default=None, max_length=100, index=True)  # ETA submission reference
    state: EtaDocumentState = Field(
        default=EtaDocumentState.DRAFT,
        sa_column=Column(sa.String(30), nullable=False, default=EtaDocumentState.DRAFT, index=True),
    )
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    canonical_string_hash: str | None = Field(default=None, max_length=64)
    signature_b64: str | None = Field(default=None)
    signature_type: str = Field(default="I", max_length=1)  # I | S
    attempts: int = Field(default=0)
    next_attempt_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    submitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    accepted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    rejected_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    validation_errors: dict | list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    translated_errors: dict | list | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    date_time_issued: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    deadline_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    public_url: str | None = Field(default=None, max_length=255)
    qr_payload: str | None = Field(default=None)


class EtaSubmission(TenantBase, table=True):
    """
    A batch of documents submitted to ETA (FR-535).
    """
    __tablename__ = "eta_submissions"
    __table_args__ = ({"schema": "tenant"},)

    tenant_id: UUID = Field(index=True)
    submission_uuid: str = Field(max_length=100, unique=True, index=True)
    document_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    document_count: int = Field(default=0)
    submitted_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=DateTime(timezone=True),
    )
    response_status: int | None = Field(default=None)
    accepted_count: int = Field(default=0)
    rejected_count: int = Field(default=0)
    callback_received_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
