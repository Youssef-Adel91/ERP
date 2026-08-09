"""
app/core/models/mixins.py — Universal Document Lifecycle Mixin (Phase 4a)

Enforces a single document state machine, fraud-prevention content hashing (FR-1212),
and lifecycle timestamps across all approvable/postable documents.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class DocumentState(StrEnum):
    """
    Universal state machine for all approvable documents across OmniERP.
    No document type gets bespoke lifecycle states (FR-1201).
    """
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    WITHDRAWN = "WITHDRAWN"
    REVERSED = "REVERSED"
    CLOSED = "CLOSED"


def compute_content_hash(data: dict) -> str:
    """
    Compute SHA256 hex digest of approvable content (FR-1212).
    Uses deterministic JSON serialization (sorted keys, stringified values).
    Only approvable fields should be passed in `data` (lines, amounts, contact, dates).
    """
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DocumentLifecycleMixin(SQLModel):
    """
    Universal mixin for all approvable and postable documents across OmniERP.
    Enforces a uniform state machine, content hashing for fraud prevention (FR-1212),
    and full lifecycle timestamping.
    """
    state: DocumentState = Field(
        default=DocumentState.DRAFT,
        sa_type=sa.Enum(
            DocumentState,
            name="documentstate",
            schema="tenant",
            create_type=False,
        ),
        sa_column_kwargs={
            "default": DocumentState.DRAFT,
            "nullable": False,
        },
    )
    content_hash: str | None = Field(default=None, max_length=64, index=True)
    submitted_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    submitted_by: UUID | None = Field(default=None, index=True)
    approved_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    posted_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    reversal_of_id: UUID | None = Field(default=None, index=True)

    def compute_approvable_content_hash(self, approvable_data: dict) -> str:
        """Helper to compute and return SHA256 hash of approvable data."""
        return compute_content_hash(approvable_data)
