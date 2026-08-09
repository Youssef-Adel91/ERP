"""
tests/eta/test_receipts_and_pdf.py — Unit & Integration Tests for ETA e-Receipts (B2C) & Local PDF/QR Generation (Phase 5 - Step 5)

Tests:
  1. Receipt Chaining: Automatic resolution of previous_uuid.
  2. 72-Hour Offline Window (FR-574): Flagging late_on_arrival while still batching late receipts.
  3. Batch Serialization (FR-570): Hashing and signing the entire batch structure.
  4. F-4 External Idempotency: Handling network timeout on receipt batch submission.
  5. Local PDF & QR Rendering (F-5, FR-575, FR-576): Self-rendered A4 and 80mm thermal PDFs embedding local verification QR codes.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.eta.exceptions import EtaSubmissionTimeoutError
from app.modules.eta.models.core import EtaEnvironment, EtaTenantConfig
from app.modules.eta.models.receipts import (
    EtaReceiptBatchState,
    EtaReceiptState,
)
from app.modules.eta.services.gateway import EtaGateway
from app.modules.eta.services.pdf import (
    generate_local_invoice_pdf,
    generate_qr_code_image,
)
from app.modules.eta.services.receipts import (
    build_and_sign_receipt_batch,
    prepare_eta_receipt,
    submit_receipt_batch,
)

pytestmark = pytest.mark.asyncio


class MockSuccessReceiptGateway(EtaGateway):
    """Mock ETA Gateway that returns 200/202 with a submissionId."""

    async def submit_receipts(
        self,
        tenant_config: EtaTenantConfig,
        submission_payload: dict[str, Any],
        max_wait: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "submissionId": "ETA-RCT-SUB-999888",
            "status": "Accepted",
        }


class MockTimeoutReceiptGateway(EtaGateway):
    """Mock ETA Gateway that simulates a network timeout during receipt batch submission."""

    async def submit_receipts(
        self,
        tenant_config: EtaTenantConfig,
        submission_payload: dict[str, Any],
        max_wait: float = 0.0,
    ) -> dict[str, Any]:
        raise asyncio.TimeoutError("Simulated ETA network timeout during receipt submission")


async def test_receipt_chaining_previous_uuid(db_session: AsyncSession):
    """
    Test that prepare_eta_receipt automatically links the previous receipt's UUID
    for ETA receipt chaining.
    """
    tenant_id = uuid4()
    now = datetime.now(UTC)

    # 1. First receipt (no previous receipt exists)
    rcp1 = await prepare_eta_receipt(
        session=db_session,
        tenant_id=tenant_id,
        internal_doc_id="RCP-1001",
        receipt_number="RCP-1001",
        date_time_issued=now - timedelta(hours=2),
        payload_json={"totalAmount": 150.0, "receiptLines": []},
    )
    assert rcp1.previous_uuid == ""
    assert rcp1.late_on_arrival is False

    # Simulate acceptance of receipt 1 with an ETA-assigned UUID
    rcp1.uuid = "UUID-ETA-1001"
    rcp1.state = EtaReceiptState.ACCEPTED
    db_session.add(rcp1)
    await db_session.commit()

    # 2. Second receipt should chain to rcp1's UUID
    rcp2 = await prepare_eta_receipt(
        session=db_session,
        tenant_id=tenant_id,
        internal_doc_id="RCP-1002",
        receipt_number="RCP-1002",
        date_time_issued=now - timedelta(hours=1),
        payload_json={"totalAmount": 300.0, "receiptLines": []},
    )
    assert rcp2.previous_uuid == "UUID-ETA-1001"
    assert rcp2.late_on_arrival is False


async def test_receipt_72_hour_offline_window_flagging_late_arrival(db_session: AsyncSession):
    """
    Test that receipts issued > 72 hours ago (offline POS sync delay) are flagged
    as late_on_arrival = True, but are STILL included in the batch (FR-574).
    """
    tenant_id = uuid4()
    now = datetime.now(UTC)

    # Create tenant config for signing
    cfg = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="test-client",
        taxpayer_rin="123456789",
        activity_code="4620",
        branch_id="0",
        signing_provider="LOCAL_AGENT",
    )
    db_session.add(cfg)
    await db_session.commit()

    # On-time receipt (10 hours ago)
    rcp_ontime = await prepare_eta_receipt(
        session=db_session,
        tenant_id=tenant_id,
        internal_doc_id="RCP-2001",
        receipt_number="RCP-2001",
        date_time_issued=now - timedelta(hours=10),
        payload_json={"totalAmount": 100.0},
    )
    assert rcp_ontime.late_on_arrival is False

    # Late receipt (80 hours ago) -> offline POS delayed sync
    rcp_late = await prepare_eta_receipt(
        session=db_session,
        tenant_id=tenant_id,
        internal_doc_id="RCP-2002",
        receipt_number="RCP-2002",
        date_time_issued=now - timedelta(hours=80),
        payload_json={"totalAmount": 250.0},
    )
    assert rcp_late.late_on_arrival is True

    # Build and sign the batch
    batch = await build_and_sign_receipt_batch(
        session=db_session,
        tenant_id=tenant_id,
        pos_terminal_id="POS-CAIRO-01",
        receipt_ids=["RCP-2001", "RCP-2002"],
    )

    assert batch.receipt_count == 2
    assert batch.state == EtaReceiptBatchState.SIGNED
    assert batch.batch_canonical_hash is not None
    assert len(batch.batch_canonical_hash) == 64  # SHA-256 uppercase hex
    assert batch.signature_b64 is not None

    # Verify both receipts transitioned to BATCHED
    await db_session.refresh(rcp_ontime)
    await db_session.refresh(rcp_late)
    assert rcp_ontime.state == EtaReceiptState.BATCHED
    assert rcp_late.state == EtaReceiptState.BATCHED
    assert rcp_ontime.batch_id == batch.id
    assert rcp_late.batch_id == batch.id


async def test_submit_receipt_batch_timeout_f4_external_idempotency(db_session: AsyncSession):
    """
    Test F-4 External Idempotency on B2C e-Receipt batch submission timeout:
    When a timeout occurs, the batch and all receipts transition to SUBMIT_UNCERTAIN
    and no blind retries occur.
    """
    tenant_id = uuid4()
    now = datetime.now(UTC)

    cfg = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="test-client",
        taxpayer_rin="123456789",
        activity_code="4620",
        branch_id="0",
        signing_provider="LOCAL_AGENT",
    )
    db_session.add(cfg)
    await db_session.commit()

    await prepare_eta_receipt(
        session=db_session,
        tenant_id=tenant_id,
        internal_doc_id="RCP-3001",
        receipt_number="RCP-3001",
        date_time_issued=now - timedelta(hours=5),
        payload_json={"totalAmount": 500.0},
    )

    batch = await build_and_sign_receipt_batch(
        session=db_session,
        tenant_id=tenant_id,
        pos_terminal_id="POS-ALEX-01",
        receipt_ids=["RCP-3001"],
    )

    timeout_gateway = MockTimeoutReceiptGateway()

    with pytest.raises(EtaSubmissionTimeoutError) as exc_info:
        await submit_receipt_batch(
            session=db_session,
            tenant_id=tenant_id,
            batch_id=batch.id,
            gateway=timeout_gateway,
        )

    assert "F-4" in str(exc_info.value)

    await db_session.refresh(batch)
    assert batch.state == EtaReceiptBatchState.SUBMIT_UNCERTAIN
    assert batch.submission_uuid is not None
    assert batch.submission_uuid.startswith("UNCERTAIN-")


async def test_generate_local_invoice_pdf_a4_and_thermal(db_session: AsyncSession):
    """
    Test self-rendered Arabic PDF and QR code generation (F-5, FR-575, FR-576).
    Verifies that we can generate compliant A4 and 80mm thermal PDFs locally without
    hitting ETA's Get Document Printout rate limits (1 req/5s).
    """
    tenant_id = uuid4()
    now = datetime.now(UTC)

    rcp = await prepare_eta_receipt(
        session=db_session,
        tenant_id=tenant_id,
        internal_doc_id="RCP-4001",
        receipt_number="RCP-4001",
        date_time_issued=now,
        payload_json={
            "totalAmount": 450.0,
            "receiptLines": [
                {"description": "Arabic Coffee Standard", "quantity": 2, "total": 200.0},
                {"description": "Egyptian Tea Premium", "quantity": 5, "total": 250.0},
            ],
        },
    )
    rcp.uuid = "550e8400-e29b-41d4-a716-446655440000"
    rcp.public_url = "https://invoicing.eta.gov.eg/receipts/550e8400-e29b-41d4-a716-446655440000/share"
    db_session.add(rcp)
    await db_session.commit()

    # Test QR Code PNG Generation (FR-576)
    qr_bytes = generate_qr_code_image(rcp.public_url)
    assert qr_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Test A4 layout PDF rendering (F-5)
    pdf_a4 = await generate_local_invoice_pdf(
        session=db_session,
        tenant_id=tenant_id,
        invoice_id=rcp.id,
        layout="A4",
    )
    assert pdf_a4.startswith(b"%PDF-1.")
    assert len(pdf_a4) > 1000

    # Test 80mm thermal POS layout PDF rendering (FR-575)
    pdf_thermal = await generate_local_invoice_pdf(
        session=db_session,
        tenant_id=tenant_id,
        invoice_id=rcp.id,
        layout="THERMAL_80MM",
    )
    assert pdf_thermal.startswith(b"%PDF-1.")
    assert len(pdf_thermal) > 500
