"""
tests/eta/test_submission_and_callbacks.py — Unit & Integration Tests for ETA Submission Engine & Callbacks (Phase 5 - Step 4)

Tests:
  1. Successful batch submission transitioning EtaDocument state to SUBMITTED (FR-535).
  2. External Idempotency (F-4): Simulated network timeout transitioning state to SUBMIT_UNCERTAIN without blind retry.
  3. Webhook Callback endpoint (PUT /notifications/documents) returning 202 Accepted immediately (FR-550, FR-552).
  4. Rejection Translation & State Updates: Translating ETA rejection codes to Arabic with actionable deep links (FR-560)
     and returning the internal ERP SalesInvoice to DRAFT state for fixing (FR-562).
  5. Acceptance Webhook Callback transitioning EtaDocument state to ACCEPTED.
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.eta.exceptions import EtaSubmissionTimeoutError, EtaTimeoutError
from app.modules.eta.models.core import (
    EtaDocument,
    EtaDocumentState,
    EtaEnvironment,
    EtaTenantConfig,
)
from app.modules.eta.services.gateway import EtaGateway
from app.modules.eta.services.submission import submit_eta_batch
from app.modules.eta.services.translation import (
    process_document_status_event,
    translate_eta_error,
)
from app.modules.sales.models.core import SalesOrder
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus

pytestmark = pytest.mark.asyncio


class MockSuccessEtaGateway(EtaGateway):
    """Mock ETA Gateway that returns 202 Accepted with a submissionId."""

    async def submit_documents(
        self,
        tenant_config: EtaTenantConfig,
        submission_payload: dict[str, Any],
        max_wait: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "submissionId": "SUB-TEST-SUCCESS-987654",
            "acceptedDocuments": [
                {"internalId": doc.get("internalID")}
                for doc in submission_payload.get("documents", [])
            ],
        }


class MockTimeoutEtaGateway(EtaGateway):
    """Mock ETA Gateway that simulates a network timeout during POST /api/v1/documentssubmissions."""

    async def submit_documents(
        self,
        tenant_config: EtaTenantConfig,
        submission_payload: dict[str, Any],
        max_wait: float = 0.0,
    ) -> dict[str, Any]:
        raise EtaTimeoutError("Connection timed out while sending batch to Egyptian Tax Authority.")


async def test_submit_eta_batch_success_transitions_to_submitted(db_session: AsyncSession):
    """
    Verify successful batch submission (FR-535):
      - Multiple SIGNED documents are packaged into a batch.
      - Upon receiving submissionId from ETA, EtaDocument records transition to SUBMITTED.
    """
    tenant_id = uuid4()

    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="client_batch_test",
        client_secret_ref="vault://secrets/eta/secret",
        taxpayer_rin="300400500",
        activity_code="4610",
    )
    db_session.add(tenant_config)

    doc1 = EtaDocument(
        tenant_id=tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id="INV-BATCH-001",
        eta_document_type="I",
        eta_document_type_version="1.0",
        state=EtaDocumentState.SIGNED,
        payload_json={"internalID": "INV-BATCH-001", "documentType": "I"},
        canonical_string_hash="A" * 64,
        signature_b64="MOCK_SIGNATURE_1",
    )
    doc2 = EtaDocument(
        tenant_id=tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id="INV-BATCH-002",
        eta_document_type="I",
        eta_document_type_version="1.0",
        state=EtaDocumentState.SIGNED,
        payload_json={"internalID": "INV-BATCH-002", "documentType": "I"},
        canonical_string_hash="B" * 64,
        signature_b64="MOCK_SIGNATURE_2",
    )
    db_session.add(doc1)
    db_session.add(doc2)
    await db_session.commit()

    mock_gw = MockSuccessEtaGateway()
    submission = await submit_eta_batch(
        session=db_session,
        tenant_id=tenant_id,
        document_ids=["INV-BATCH-001", "INV-BATCH-002"],
        gateway=mock_gw,
    )

    assert submission.response_status == 202
    assert submission.submission_uuid == "SUB-TEST-SUCCESS-987654"
    assert submission.document_count == 2

    # Verify both documents transitioned to SUBMITTED state
    assert doc1.state == EtaDocumentState.SUBMITTED
    assert doc1.submission_uuid == "SUB-TEST-SUCCESS-987654"
    assert doc2.state == EtaDocumentState.SUBMITTED
    assert doc2.submission_uuid == "SUB-TEST-SUCCESS-987654"


async def test_submit_eta_batch_timeout_f4_external_idempotency(db_session: AsyncSession):
    """
    Verify External Idempotency (F-4):
      - If an HTTP or network timeout occurs during ETA submission, we CANNOT know if ETA
        processed the batch.
      - Documents MUST transition to SUBMIT_UNCERTAIN state.
      - next_attempt_at is cleared to prevent blind retries and duplicate invoice penalties.
    """
    tenant_id = uuid4()

    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="client_timeout_test",
        client_secret_ref="vault://secrets/eta/secret",
        taxpayer_rin="400500600",
        activity_code="4610",
    )
    db_session.add(tenant_config)

    doc = EtaDocument(
        tenant_id=tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id="INV-TIMEOUT-100",
        eta_document_type="I",
        eta_document_type_version="1.0",
        state=EtaDocumentState.SIGNED,
        payload_json={"internalID": "INV-TIMEOUT-100"},
        canonical_string_hash="C" * 64,
        signature_b64="MOCK_SIGNATURE_3",
    )
    db_session.add(doc)
    await db_session.commit()

    mock_gw = MockTimeoutEtaGateway()

    with pytest.raises(EtaSubmissionTimeoutError) as exc_info:
        await submit_eta_batch(
            session=db_session,
            tenant_id=tenant_id,
            document_ids=["INV-TIMEOUT-100"],
            gateway=mock_gw,
        )

    assert "SUBMIT_UNCERTAIN" in str(exc_info.value)
    assert doc.state == EtaDocumentState.SUBMIT_UNCERTAIN
    assert doc.next_attempt_at is None  # Proves blind automatic retry is disabled (F-4)
    assert doc.submission_uuid is not None
    assert doc.submission_uuid.startswith("UNCERTAIN-")


async def test_eta_error_translation_dictionary(db_session: AsyncSession):
    """
    Verify ETA Rejection Translation Dictionary (FR-560):
      - Rejection codes are mapped to Arabic strings with actionable deep links.
    """
    trans_4049 = translate_eta_error("4049")
    assert trans_4049["error_code"] == "4049"
    assert "كود الصنف غير مسجل" in trans_4049["title_ar"]
    assert "اضغط هنا لإضافة كود GS1" in trans_4049["action_ar"]
    assert trans_4049["deep_link"] == "/app/eta/codes"

    trans_4010 = translate_eta_error("4010")
    assert trans_4010["error_code"] == "4010"
    assert "شهادة التوقيع الإلكتروني منتهية الصلاحية" in trans_4010["title_ar"]
    assert trans_4010["deep_link"] == "/app/eta/settings/signing"


async def test_eta_webhook_callback_202_and_rejection_processing(
    db_session: AsyncSession,
    client: AsyncClient,
):
    """
    Verify Webhook Callback Endpoint (FR-550, FR-552) and Rejection Consumer (FR-560, FR-562):
      1. PUT /notifications/documents returns 202 Accepted immediately without blocking.
      2. Consumer processes rejection event -> EtaDocument transitions to REJECTED.
      3. translated_errors is populated with Arabic actionable diagnostics (FR-560).
      4. Internal ERP SalesInvoice is returned to DRAFT state for fixing (FR-562).
    """
    tenant_id = uuid4()
    contact_id = uuid4()

    # Create SalesOrder and SalesInvoice in POSTED state
    order = SalesOrder(order_number="ORD-WEBHOOK-200", contact_id=contact_id)
    db_session.add(order)
    await db_session.flush()

    invoice = SalesInvoice(
        invoice_number="INV-REJECTED-200",
        order_id=order.id,
        contact_id=contact_id,
        issue_date=date.today(),
        subtotal=Decimal("1000.0000"),
        tax_total=Decimal("140.0000"),
        grand_total=Decimal("1140.0000"),
        status=SalesInvoiceStatus.POSTED,  # Already posted invoice
    )
    db_session.add(invoice)

    doc = EtaDocument(
        tenant_id=tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id="INV-REJECTED-200",
        eta_document_type="I",
        eta_document_type_version="1.0",
        state=EtaDocumentState.SUBMITTED,
        uuid="ETA-UUID-REJECTED-200",
        submission_uuid="SUB-REJECTED-200",
    )
    db_session.add(doc)
    await db_session.commit()

    webhook_payload = {
        "submissionId": "SUB-REJECTED-200",
        "uuid": "ETA-UUID-REJECTED-200",
        "internalId": "INV-REJECTED-200",
        "status": "Invalid",
        "validationResults": {
            "status": "Invalid",
            "validationSteps": [
                {
                    "name": "ITEM_CODE_VALIDATION",
                    "status": "Invalid",
                    "error": {
                        "errorCode": "4049",
                        "errorMessage": "Item code EG-100200300-INVALID is not registered or inactive.",
                    },
                },
                {
                    "name": "SIGNATURE_VALIDATION",
                    "status": "Invalid",
                    "error": {
                        "errorCode": "4010",
                        "errorMessage": "Signing certificate has expired.",
                    },
                },
            ],
        },
    }

    # 1. Test Fast Return (FR-552) via FastAPI endpoint PUT /notifications/documents
    response = await client.put(
        "/notifications/documents",
        json=webhook_payload,
        headers={"X-Tenant-ID": str(tenant_id)},
    )
    assert response.status_code == 202
    res_json = response.json()
    assert res_json["status"] == "ACCEPTED"
    assert "FR-552" in res_json["message"]

    # 2. Directly process the webhook event to verify consumer state transitions (FR-560, FR-562)
    processed_doc = await process_document_status_event(
        session=db_session,
        tenant_id=tenant_id,
        event_payload=webhook_payload,
    )

    assert processed_doc is not None
    assert processed_doc.state == EtaDocumentState.REJECTED
    assert processed_doc.rejected_at is not None

    # Verify translated Arabic errors (FR-560)
    assert len(processed_doc.translated_errors) == 2
    err_4049 = processed_doc.translated_errors[0]
    assert err_4049["error_code"] == "4049"
    assert "كود الصنف غير مسجل" in err_4049["title_ar"]
    assert "اضغط هنا لإضافة كود GS1" in err_4049["action_ar"]
    assert err_4049["deep_link"] == "/app/eta/codes"

    err_4010 = processed_doc.translated_errors[1]
    assert err_4010["error_code"] == "4010"
    assert "شهادة التوقيع الإلكتروني منتهية الصلاحية" in err_4010["title_ar"]
    assert err_4010["deep_link"] == "/app/eta/settings/signing"

    # Verify internal ERP SalesInvoice was returned to DRAFT state for fixing (FR-562)
    await db_session.refresh(invoice)
    assert invoice.status == SalesInvoiceStatus.DRAFT


async def test_eta_webhook_callback_accepted_transitions_to_accepted(db_session: AsyncSession):
    """
    Verify Acceptance Webhook Callback:
      - When ETA sends status 'Valid', EtaDocument transitions to ACCEPTED.
      - Stores UUID, longId, and publicUrl.
    """
    tenant_id = uuid4()

    doc = EtaDocument(
        tenant_id=tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id="INV-ACCEPTED-300",
        eta_document_type="I",
        eta_document_type_version="1.0",
        state=EtaDocumentState.SUBMITTED,
        submission_uuid="SUB-ACCEPTED-300",
    )
    db_session.add(doc)
    await db_session.commit()

    webhook_payload = {
        "submissionId": "SUB-ACCEPTED-300",
        "uuid": "ETA-UUID-ACCEPTED-300",
        "internalId": "INV-ACCEPTED-300",
        "status": "Valid",
        "longId": "LONG-VERIFICATION-ID-300",
        "publicUrl": "https://preprod.eta.gov.eg/documents/300/share",
        "validationResults": {"status": "Valid", "validationSteps": []},
    }

    processed_doc = await process_document_status_event(
        session=db_session,
        tenant_id=tenant_id,
        event_payload=webhook_payload,
    )

    assert processed_doc is not None
    assert processed_doc.state == EtaDocumentState.ACCEPTED
    assert processed_doc.uuid == "ETA-UUID-ACCEPTED-300"
    assert processed_doc.long_id == "LONG-VERIFICATION-ID-300"
    assert processed_doc.public_url == "https://preprod.eta.gov.eg/documents/300/share"
    assert processed_doc.accepted_at is not None
