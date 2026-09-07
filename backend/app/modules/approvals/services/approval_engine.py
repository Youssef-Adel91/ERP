"""
app/modules/approvals/services/approval_engine.py — Universal Approval Engine Service
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.mixins import DocumentLifecycleMixin, DocumentState, compute_content_hash
from app.modules.approvals.models.core import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestState,
    ApprovalRule,
    DecisionType,
    RuleOperator,
)
from app.modules.approvals.services.exceptions import (
    ContentHashMismatchError,
    IllegalStateTransitionError,
    SegregationOfDutiesError,
)


def _evaluate_condition(operator: RuleOperator, field_value: Any, condition_value: Any) -> bool:
    """Evaluate one ApprovalRule condition against a document's field value."""
    if field_value is None:
        return False
    if operator == RuleOperator.EQ:
        return str(field_value) == str(condition_value)
    if operator == RuleOperator.IN:
        return field_value in (condition_value or [])
    if operator == RuleOperator.NOT_IN:
        return field_value not in (condition_value or [])
    # Remaining operators (gt/gte/lt/lte) are numeric comparisons.
    lhs = Decimal(str(field_value))
    rhs = Decimal(str(condition_value))
    if operator == RuleOperator.GT:
        return lhs > rhs
    if operator == RuleOperator.GTE:
        return lhs >= rhs
    if operator == RuleOperator.LT:
        return lhs < rhs
    if operator == RuleOperator.LTE:
        return lhs <= rhs
    return False


async def find_matching_rules(
    session: AsyncSession,
    document_type: str,
    fields: dict[str, Any],
) -> list[ApprovalRule]:
    """
    Returns the active `ApprovalRule`s for `document_type` whose condition
    matches `fields` (e.g. {"total_amount": Decimal("15000")}), ordered by
    `sequence_no`. An **empty list means no approval is required** — this is
    the load-bearing behavior that keeps tenants with zero configured rules
    on the exact same auto-approve path they had before the Approval Engine
    was wired into any document flow.

    A rule whose `condition_value` can't be compared to the document's field
    (e.g. a numeric operator against non-numeric data — a misconfiguration)
    is skipped rather than raised, so a bad rule can never block or crash
    document submission.
    """
    now = datetime.now(UTC)
    stmt = (
        select(ApprovalRule)
        .where(ApprovalRule.document_type == document_type, ApprovalRule.is_active == True)  # noqa: E712
        .order_by(ApprovalRule.sequence_no)
    )
    rules = (await session.execute(stmt)).scalars().all()

    matched: list[ApprovalRule] = []
    for rule in rules:
        if rule.effective_from and now < rule.effective_from:
            continue
        if rule.effective_to and now > rule.effective_to:
            continue
        try:
            if _evaluate_condition(rule.operator, fields.get(rule.condition_field), rule.condition_value):
                matched.append(rule)
        except (InvalidOperation, TypeError, ValueError):
            continue
    return matched


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
