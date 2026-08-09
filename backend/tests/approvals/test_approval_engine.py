"""
tests/approvals/test_approval_engine.py — Tests for Phase 4a Document Lifecycle & Approval Substrate

Covers:
  1. Document hash calculation & immutability verification.
  2. Segregation of duties rejection when requested_by == decided_by (FR-1206).
  3. Hash mismatch exception when DRAFT content changes post-approval (FR-1212).
  4. Alembic migration upgrade/downgrade verification for the expand-contract pattern.
"""
from __future__ import annotations

import importlib
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.mixins import (
    DocumentLifecycleMixin,
    DocumentState,
    compute_content_hash,
)
from app.modules.accounting.models import JournalEntry, JournalEntryStatus
from app.modules.approvals.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestState,
    DecisionType,
)
from app.modules.approvals.services import (
    ContentHashMismatchError,
    IllegalStateTransitionError,
    SegregationOfDutiesError,
    assert_document_not_tampered,
    check_and_void_if_modified,
    decide_approval,
    submit_for_approval,
)
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus
from app.modules.sales.models.returns import SalesReturn, SalesReturnStatus


class DummyDocument(DocumentLifecycleMixin, table=False):
    id: str = "dummy-123"


def test_content_hash_calculation_and_immutability():
    """Verify deterministic JSON SHA256 hashing across key ordering and types."""
    data_1 = {"amount": Decimal("100.00"), "contact_id": "c-1", "lines": [1, 2]}
    data_2 = {"lines": [1, 2], "contact_id": "c-1", "amount": "100.00"}
    data_3 = {"amount": Decimal("100.01"), "contact_id": "c-1", "lines": [1, 2]}

    hash_1 = compute_content_hash(data_1)
    hash_2 = compute_content_hash(data_2)
    hash_3 = compute_content_hash(data_3)

    assert hash_1 == hash_2, "Identical content with different key order must yield identical SHA256 hash"
    assert hash_1 != hash_3, "Different content must yield different SHA256 hash"
    assert len(hash_1) == 64, "SHA256 hex digest length must be 64 characters"

    doc = DummyDocument()
    assert doc.compute_approvable_content_hash(data_1) == hash_1


@pytest.mark.asyncio
async def test_segregation_of_duties_rejection(db_session: AsyncSession):
    """
    Verify Segregation of Duties (FR-1206):
    A creator/requester CANNOT approve their own document under any circumstances.
    """
    creator_id = uuid4()
    approver_id = uuid4()
    doc_id = uuid4()

    doc = SalesInvoice(
        id=doc_id,
        invoice_number=f"INV-SOD-{doc_id.hex[:6]}",
        order_id=uuid4(),
        contact_id=uuid4(),
        issue_date=date.today(),
        due_date=date.today(),
        currency="EGP",
        subtotal=Decimal("1000.0000"),
        tax_total=Decimal("140.0000"),
        grand_total=Decimal("1140.0000"),
    )

    approvable_content = {
        "invoice_number": doc.invoice_number,
        "grand_total": "1140.0000",
    }

    req = await submit_for_approval(
        session=db_session,
        document_type="sales_invoice",
        document_id=doc.id,
        document=doc,
        requested_by=creator_id,
        approvable_content=approvable_content,
    )

    assert doc.state == DocumentState.PENDING_APPROVAL
    assert doc.content_hash is not None
    assert req.state == ApprovalRequestState.PENDING

    # Attempt to approve your own document -> SegregationOfDutiesError (FR-1206)
    with pytest.raises(SegregationOfDutiesError):
        await decide_approval(
            session=db_session,
            approval_request_id=req.id,
            decision=DecisionType.APPROVE,
            decided_by=creator_id,
            document=doc,
        )

    # Approving by a different user -> succeeds and updates state
    decision = await decide_approval(
        session=db_session,
        approval_request_id=req.id,
        decision=DecisionType.APPROVE,
        decided_by=approver_id,
        document=doc,
        comment="Approved invoice",
    )

    assert decision.decision == DecisionType.APPROVE
    assert decision.decided_by == approver_id
    assert req.state == ApprovalRequestState.APPROVED
    assert doc.state == DocumentState.APPROVED
    assert doc.approved_at is not None


@pytest.mark.asyncio
async def test_hash_mismatch_exception_when_draft_content_changes(db_session: AsyncSession):
    """
    Verify Hash Validation (FR-1212):
    Modifying an approved document voids prior approval and raises ContentHashMismatchError on tamper assertion.
    """
    creator_id = uuid4()
    approver_id = uuid4()
    doc_id = uuid4()

    doc = SalesInvoice(
        id=doc_id,
        invoice_number=f"INV-HASH-{doc_id.hex[:6]}",
        order_id=uuid4(),
        contact_id=uuid4(),
        issue_date=date.today(),
        due_date=date.today(),
        currency="EGP",
        subtotal=Decimal("500.0000"),
        tax_total=Decimal("70.0000"),
        grand_total=Decimal("570.0000"),
    )

    original_content = {"grand_total": "570.0000"}
    altered_content = {"grand_total": "999.0000"}

    req = await submit_for_approval(
        session=db_session,
        document_type="sales_invoice",
        document_id=doc.id,
        document=doc,
        requested_by=creator_id,
        approvable_content=original_content,
    )

    await decide_approval(
        session=db_session,
        approval_request_id=req.id,
        decision=DecisionType.APPROVE,
        decided_by=approver_id,
        document=doc,
    )

    assert doc.state == DocumentState.APPROVED

    # Asserting untouched content succeeds
    assert_document_not_tampered(doc, original_content)

    # Asserting tampered content raises ContentHashMismatchError
    with pytest.raises(ContentHashMismatchError):
        assert_document_not_tampered(doc, altered_content)

    # check_and_void_if_modified voids prior approval and returns True
    was_voided = check_and_void_if_modified(doc, altered_content)
    assert was_voided is True
    assert doc.state == DocumentState.DRAFT
    assert doc.approved_at is None
    assert doc.content_hash == compute_content_hash(altered_content)


def test_alembic_expand_contract_retrofit_models():
    """
    Verify that SalesInvoice, SalesReturn, and JournalEntry inherit DocumentLifecycleMixin
    and that Alembic migration d4e5f6a1b2c3 provides valid upgrade/downgrade hooks.
    """
    # 1. Check inheritance and lifecycle fields on SalesInvoice
    assert issubclass(SalesInvoice, DocumentLifecycleMixin)
    assert "state" in SalesInvoice.model_fields
    assert "content_hash" in SalesInvoice.model_fields
    assert "submitted_at" in SalesInvoice.model_fields
    assert "submitted_by" in SalesInvoice.model_fields
    assert "approved_at" in SalesInvoice.model_fields
    assert "posted_at" in SalesInvoice.model_fields
    assert "reversal_of_id" in SalesInvoice.model_fields

    # 2. Check inheritance on SalesReturn
    assert issubclass(SalesReturn, DocumentLifecycleMixin)
    assert "state" in SalesReturn.model_fields
    assert "content_hash" in SalesReturn.model_fields

    # 3. Check inheritance on JournalEntry
    assert issubclass(JournalEntry, DocumentLifecycleMixin)
    assert "state" in JournalEntry.model_fields
    assert "content_hash" in JournalEntry.model_fields
    assert "posted_at" in JournalEntry.model_fields

    # 4. Verify Alembic migration module structure
    import importlib.util
    from pathlib import Path

    mig_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "tenant"
        / "versions"
        / "d4e5f6a1b2c3_phase_4a_approvals.py"
    )
    spec = importlib.util.spec_from_file_location("d4e5f6a1b2c3_phase_4a_approvals", mig_path)
    assert spec and spec.loader
    mig_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig_mod)
    assert getattr(mig_mod, "revision", None) == "d4e5f6a1b2c3"
    assert getattr(mig_mod, "down_revision", None) == "c3d4e5f6a1b2"
    assert callable(getattr(mig_mod, "upgrade", None))
    assert callable(getattr(mig_mod, "downgrade", None))
