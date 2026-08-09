"""
app/modules/approvals/services/approval_engine.py — Universal Approval Engine Service
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.mixins import DocumentLifecycleMixin, DocumentState, compute_content_hash
from app.modules.approvals.models.core import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestState,
    DecisionType,
)
from app.modules.approvals.services.exceptions import (
    ContentHashMismatchError,
    IllegalStateTransitionError,
    SegregationOfDutiesError,
)


async def submit_for_approval(
    session: AsyncSession,
    document_type: str,
    document_id: UUID,
    document: DocumentLifecycleMixin,
    requested_by: UUID,
    approvable_content: dict,
    rule_id: UUID | None = None,
    rule_version: int | None = None,
    due_at: datetime | None = None,
) -> ApprovalRequest:
    """
    Submit a document for approval.
    Enforces content hashing (FR-1212) and transitions document to PENDING_APPROVAL.
    """
    if document.state != DocumentState.DRAFT and document.state != DocumentState.REJECTED:
        raise IllegalStateTransitionError(
            f"Cannot submit document for approval from state {document.state}. Must be DRAFT or REJECTED."
        )

    content_hash = compute_content_hash(approvable_content)
    document.content_hash = content_hash
    document.state = DocumentState.PENDING_APPROVAL
    document.submitted_at = datetime.now(UTC)
    document.submitted_by = requested_by

    req = ApprovalRequest(
        document_type=document_type,
        document_id=document_id,
        document_content_hash=content_hash,
        state=ApprovalRequestState.PENDING,
        requested_by=requested_by,
        rule_id=rule_id,
        rule_version=rule_version,
        due_at=due_at,
    )
    session.add(req)
    session.add(document)
    await session.flush()
    return req


async def decide_approval(
    session: AsyncSession,
    approval_request_id: UUID,
    decision: DecisionType,
    decided_by: UUID,
    comment: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    document: DocumentLifecycleMixin | None = None,
) -> ApprovalDecision:
    """
    Record an approval or rejection decision (FR-1211 immutable audit).
    Enforces Segregation of Duties (FR-1206) and Hash Validation (FR-1212).
    """
    stmt = select(ApprovalRequest).where(ApprovalRequest.id == approval_request_id)
    result = await session.execute(stmt)
    approval_request = result.scalar_one_or_none()

    if not approval_request:
        raise ValueError(f"ApprovalRequest {approval_request_id} not found.")

    # Segregation of Duties (FR-1206): Creator can NEVER approve their own document
    if approval_request.requested_by == decided_by:
        raise SegregationOfDutiesError(
            "Segregation of Duties (FR-1206): Creator cannot approve their own document."
        )
    if document and document.submitted_by == decided_by:
        raise SegregationOfDutiesError(
            "Segregation of Duties (FR-1206): Creator cannot approve their own document."
        )
    if approval_request.delegated_from_user_id and approval_request.delegated_from_user_id == decided_by:
        raise SegregationOfDutiesError(
            "Segregation of Duties (FR-1206): Cannot approve a document delegated from yourself."
        )

    if approval_request.state != ApprovalRequestState.PENDING:
        raise IllegalStateTransitionError(
            f"Cannot decide on ApprovalRequest in state {approval_request.state}. Must be pending."
        )

    # Hash Validation (FR-1212): If document content was altered after approval request, reject/void
    if document and document.content_hash != approval_request.document_content_hash:
        raise ContentHashMismatchError(
            "Document content hash mismatch! Document was altered after approval was requested (FR-1212)."
        )

    # Record immutable audit decision (FR-1211)
    audit_decision = ApprovalDecision(
        approval_request_id=approval_request.id,
        decision=decision,
        decided_by=decided_by,
        comment=comment,
        document_content_hash=approval_request.document_content_hash,
        ip_address=ip_address,
        user_agent=user_agent,
        decided_at=datetime.now(UTC),
    )
    session.add(audit_decision)

    if decision == DecisionType.APPROVE:
        approval_request.state = ApprovalRequestState.APPROVED
        approval_request.resolved_at = datetime.now(UTC)
        approval_request.resolved_by = decided_by
        approval_request.resolution_comment = comment
        if document:
            document.state = DocumentState.APPROVED
            document.approved_at = datetime.now(UTC)
            session.add(document)
    elif decision == DecisionType.REJECT:
        approval_request.state = ApprovalRequestState.REJECTED
        approval_request.resolved_at = datetime.now(UTC)
        approval_request.resolved_by = decided_by
        approval_request.resolution_comment = comment
        if document:
            document.state = DocumentState.DRAFT
            document.approved_at = None
            session.add(document)

    session.add(approval_request)
    await session.flush()
    return audit_decision


def check_and_void_if_modified(
    document: DocumentLifecycleMixin,
    new_approvable_content: dict,
) -> bool:
    """
    FR-1212: Modifying an approved document in draft state voids the prior approval.
    Returns True if a prior approval/hash was voided due to alteration.
    """
    new_hash = compute_content_hash(new_approvable_content)
    if document.content_hash and document.content_hash != new_hash:
        if document.state in (DocumentState.APPROVED, DocumentState.PENDING_APPROVAL):
            document.state = DocumentState.DRAFT
            document.approved_at = None
        document.content_hash = new_hash
        return True
    return False


def assert_document_not_tampered(
    document: DocumentLifecycleMixin,
    current_approvable_content: dict,
) -> None:
    """
    Assert that the document content hash matches its approvable fields.
    Raises ContentHashMismatchError if tampered or modified after approval (FR-1212).
    """
    current_hash = compute_content_hash(current_approvable_content)
    if document.content_hash and document.content_hash != current_hash:
        raise ContentHashMismatchError(
            "Document content hash mismatch! Altering an approved document voids prior approval (FR-1212)."
        )
