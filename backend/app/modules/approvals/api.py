"""
app/modules/approvals/api.py — Approval Engine REST API

This module's domain layer (models/core.py + services/approval_engine.py)
already existed fully written but had zero HTTP exposure. This adds the
missing router.

Two supported flows:
  1. Rule management — configure who must approve what (ApprovalRule CRUD).
  2. Generic approval requests — any document_type/document_id pair can be
     submitted for approval and decided on. This does NOT yet integrate with
     the full DocumentLifecycleMixin state sync (that requires each source
     module's own models to adopt the mixin, a larger follow-up). What IS
     fully real here: content-hash tamper detection, segregation-of-duties
     enforcement (a creator can never approve their own request), and an
     immutable decision audit trail — all backed by the existing service.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.core.models.mixins import DocumentLifecycleMixin, compute_content_hash
from app.modules.approvals.models.core import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestState,
    ApprovalRule,
    ApproverType,
    DecisionType,
    RuleOperator,
)
from app.modules.approvals.services.approval_engine import decide_approval
from app.modules.approvals.services.exceptions import (
    ContentHashMismatchError,
    IllegalStateTransitionError,
    SegregationOfDutiesError,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/approvals", tags=["Approvals"])

# Document types whose model has adopted DocumentLifecycleMixin (see
# app/core/models/mixins.py) and therefore has its `state` synced back to
# APPROVED/DRAFT here when a decision is recorded. A document_type NOT in
# this map still gets a fully real, audited approve/reject decision — it
# just has no source-module state of its own to sync (per this module's
# original "generic requests" design, see this file's module docstring).
# Registered lazily (inside decide(), not at import time) to avoid a
# hard import-time dependency from approvals -> purchasing.
def _resolve_document_model(document_type: str) -> type[DocumentLifecycleMixin] | None:
    if document_type == "purchase_order":
        from app.modules.purchasing.models.core import PurchaseOrder

        return PurchaseOrder
    return None


# ── Approval Rules ────────────────────────────────────────────────────────────


class ApprovalRuleCreate(BaseModel):
    document_type: str
    condition_field: str
    operator: RuleOperator
    condition_value: Any = None
    approver_type: ApproverType
    approver_ref: UUID
    sequence_no: int = 1
    is_mandatory: bool = True


@router.post("/rules", response_model=ApprovalRule, status_code=status.HTTP_201_CREATED)
async def create_rule(
    data: ApprovalRuleCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    rule = ApprovalRule(**data.model_dump(), created_by=current_user.id)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.get("/rules", response_model=list[ApprovalRule])
async def list_rules(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    document_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    q = select(ApprovalRule)
    if document_type:
        q = q.where(ApprovalRule.document_type == document_type)
    if is_active is not None:
        q = q.where(ApprovalRule.is_active == is_active)
    result = await session.execute(q.order_by(ApprovalRule.sequence_no))
    return result.scalars().all()


class ApprovalRuleUpdate(BaseModel):
    condition_field: str | None = None
    operator: RuleOperator | None = None
    condition_value: Any = None
    approver_type: ApproverType | None = None
    approver_ref: UUID | None = None
    sequence_no: int | None = None
    is_mandatory: bool | None = None
    is_active: bool | None = None


@router.patch("/rules/{id}", response_model=ApprovalRule)
async def update_rule(
    id: UUID,
    data: ApprovalRuleUpdate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Edit a rule, or deactivate it (is_active=False) instead of deleting —
    was previously entirely missing, so a rule created with a mistaken
    approver_ref or condition could never be fixed or turned off short of
    a direct DB edit.
    """
    rule = await session.get(ApprovalRule, id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval rule not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


# ── Approval Requests ─────────────────────────────────────────────────────────


class ApprovalRequestCreate(BaseModel):
    document_type: str
    document_id: UUID
    approvable_content: dict[str, Any]
    rule_id: UUID | None = None
    due_at: datetime | None = None


@router.post("/requests", response_model=ApprovalRequest, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: ApprovalRequestCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Submits a document (any type) for approval. Computes a SHA-256 content
    hash (FR-1212) so a later edit to the same document can be detected as
    tampering after the fact.
    """
    req = ApprovalRequest(
        document_type=data.document_type,
        document_id=data.document_id,
        document_content_hash=compute_content_hash(data.approvable_content),
        state=ApprovalRequestState.PENDING,
        requested_by=current_user.id,
        rule_id=data.rule_id,
        due_at=data.due_at,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


@router.get("/requests", response_model=list[ApprovalRequest])
async def list_requests(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    document_type: str | None = Query(default=None),
    state: ApprovalRequestState | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(ApprovalRequest)
    if document_type:
        q = q.where(ApprovalRequest.document_type == document_type)
    if state:
        q = q.where(ApprovalRequest.state == state)
    q = q.order_by(ApprovalRequest.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/requests/{id}", response_model=ApprovalRequest)
async def get_request(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    req = await session.get(ApprovalRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return req


class ApprovalDecisionIn(BaseModel):
    decision: DecisionType
    comment: str | None = None


@router.post("/requests/{id}/decide", response_model=ApprovalDecision)
async def decide(
    id: UUID,
    data: ApprovalDecisionIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Approve or reject a pending request. Enforces segregation of duties
    (FR-1206): the person who requested approval can never decide on it,
    regardless of role.

    For document types whose model has adopted `DocumentLifecycleMixin`
    (currently: `purchase_order`), this also syncs the source document's
    `state` — APPROVE -> APPROVED, REJECT -> back to DRAFT so it can be
    edited and resubmitted. Other document types only get the audited
    decision recorded here, with no source-module state to sync.
    """
    approval_request = await session.get(ApprovalRequest, id)
    if not approval_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")

    document = None
    model_cls = _resolve_document_model(approval_request.document_type)
    if model_cls is not None:
        document = await session.get(model_cls, approval_request.document_id)

    try:
        decision = await decide_approval(
            session=session,
            approval_request_id=id,
            decision=data.decision,
            decided_by=current_user.id,
            comment=data.comment,
            document=document,
        )
        await session.commit()
        return decision
    except SegregationOfDutiesError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IllegalStateTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ContentHashMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/requests/{id}/withdraw", response_model=ApprovalRequest)
async def withdraw_request(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """
    Lets the original requester pull back their own PENDING request (e.g.
    it was raised in error, or the underlying document changed and needs
    to be resubmitted). Previously there was no way to cancel a request
    once created — only approve/reject, both of which require someone
    ELSE to act. Restricted to the requester so it can't be used to dodge
    a rejection in progress by an approver other than the requester.
    """
    req = await session.get(ApprovalRequest, id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
    if req.requested_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the original requester can withdraw this request.",
        )
    if req.state != ApprovalRequestState.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only a PENDING request can be withdrawn (current state: {req.state.value}).",
        )
    req.state = ApprovalRequestState.WITHDRAWN
    req.resolved_at = datetime.utcnow()
    req.resolved_by = current_user.id
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req
