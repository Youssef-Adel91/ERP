"""
app/modules/approvals/models/core.py — Phase 4a Approval Substrate ORM Models
"""
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Index
from sqlmodel import Field, Relationship

from app.core.db.base import TenantBase


# ── Enumerations ──────────────────────────────────────────────────────────────

class RuleOperator(StrEnum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    IN = "in"
    NOT_IN = "not_in"


class ApproverType(StrEnum):
    SPECIFIC_USER = "specific_user"
    ROLE = "role"
    CREATOR_MANAGER = "creator_manager"
    APPROVAL_GROUP = "approval_group"


class ApprovalRequestState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class DecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


# ── Approval Rule ─────────────────────────────────────────────────────────────

class ApprovalRule(TenantBase, table=True):
    __tablename__ = "approval_rules"
    __table_args__ = (
        Index("ix_approval_rules_doc_type_active", "document_type", "is_active"),
        {"schema": "tenant"},
    )

    document_type: str = Field(max_length=50, index=True)
    condition_field: str = Field(max_length=50)
    operator: RuleOperator = Field(
        sa_column=Column(
            sa.Enum(RuleOperator, name="ruleoperator", schema="tenant"),
            nullable=False,
        )
    )
    condition_value: Any = Field(
        default=None,
        sa_column=Column(sa.JSON, nullable=True),
    )
    approver_type: ApproverType = Field(
        sa_column=Column(
            sa.Enum(ApproverType, name="approvertype", schema="tenant"),
            nullable=False,
        )
    )
    approver_ref: UUID = Field(index=True)
    sequence_no: int = Field(default=1, index=True)
    is_mandatory: bool = Field(default=True)
    effective_from: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    effective_to: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    is_active: bool = Field(default=True, index=True)
    version: int = Field(default=1)

    requests: list["ApprovalRequest"] = Relationship(back_populates="rule")


# ── Approval Request ──────────────────────────────────────────────────────────

class ApprovalRequest(TenantBase, table=True):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_doc", "document_type", "document_id"),
        {"schema": "tenant"},
    )

    document_type: str = Field(max_length=50, index=True)
    document_id: UUID = Field(index=True)
    document_content_hash: str = Field(max_length=64)
    state: ApprovalRequestState = Field(
        default=ApprovalRequestState.PENDING,
        sa_column=Column(
            sa.Enum(
                ApprovalRequestState,
                name="approvalrequeststate",
                schema="tenant",
            ),
            default=ApprovalRequestState.PENDING,
            nullable=False,
        ),
    )
    requested_by: UUID = Field(index=True)
    due_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    rule_id: UUID | None = Field(
        default=None,
        index=True,
        foreign_key="tenant.approval_rules.id",
    )
    rule_version: int | None = Field(default=None)
    sequence_no: int = Field(default=1)
    resolved_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    resolved_by: UUID | None = Field(default=None, index=True)
    resolution_comment: str | None = Field(default=None, max_length=1000)
    delegated_from_user_id: UUID | None = Field(default=None, index=True)

    rule: Optional[ApprovalRule] = Relationship(back_populates="requests")
    decisions: list["ApprovalDecision"] = Relationship(
        back_populates="approval_request",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


# ── Approval Decision (Immutable Audit — FR-1211) ─────────────────────────────

class ApprovalDecision(TenantBase, table=True):
    """
    Immutable audit log for an approval decision (FR-1211).
    Records who, when, IP, device, comment, and the exact content hash of the document.
    """
    __tablename__ = "approval_decisions"
    __table_args__ = (
        Index("ix_approval_decisions_req", "approval_request_id"),
        Index("ix_approval_decisions_decider", "decided_by"),
        {"schema": "tenant"},
    )

    approval_request_id: UUID = Field(
        index=True,
        foreign_key="tenant.approval_requests.id",
    )
    decision: DecisionType = Field(
        sa_column=Column(
            sa.Enum(DecisionType, name="decisiontype", schema="tenant"),
            nullable=False,
        )
    )
    decided_by: UUID = Field(index=True)
    comment: str | None = Field(default=None, max_length=1000)
    document_content_hash: str = Field(max_length=64)
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = Field(default=None, max_length=512)
    decided_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=DateTime(timezone=True),
    )

    approval_request: ApprovalRequest = Relationship(
        back_populates="decisions"
    )
