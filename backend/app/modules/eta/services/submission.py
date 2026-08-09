"""
app.modules.eta.services.submission — ETA Batch Submission Engine & External Idempotency (Phase 5 - Step 4)

Implements:
  1. submit_eta_batch: Batches multiple SIGNED documents into one ETA submission payload (FR-535).
  2. External Idempotency (F-4): Catches timeout exceptions during HTTP submission and transitions
     documents to SUBMIT_UNCERTAIN state without blindly retrying, preventing duplicate invoices.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.eta.exceptions import (
    EtaException,
    EtaSubmissionTimeoutError,
    EtaTimeoutError,
)
from app.modules.eta.models.core import (
    EtaDocument,
    EtaDocumentState,
    EtaSubmission,
    EtaTenantConfig,
)
from app.modules.eta.services.gateway import EtaGateway


class EtaBatchSubmissionError(EtaException):
    """Raised when batch submission fails due to invalid state or missing config."""
    pass


async def submit_eta_batch(
    session: AsyncSession,
    tenant_id: UUID,
    document_ids: list[str],
    gateway: EtaGateway | None = None,
) -> EtaSubmission:
    """
    Submit a batch of SIGNED ETA documents to the Egyptian Tax Authority API (FR-535).

    External Idempotency (F-4):
      - If an HTTP or network timeout occurs while calling ETA, we CANNOT know if ETA received
        and queued the documents.
      - We transition all documents in the batch to `SUBMIT_UNCERTAIN` and clear `next_attempt_at`.
      - We do NOT blindly retry, preventing duplicate invoices and rejection penalties.
    """
    if not document_ids:
        raise EtaBatchSubmissionError("Cannot submit an empty list of document_ids.")

    # 1. Load active tenant config
    stmt_cfg = select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == tenant_id)
    res_cfg = await session.execute(stmt_cfg)
    tenant_config = res_cfg.scalar_one_or_none()
    if not tenant_config:
        raise EtaBatchSubmissionError(f"No EtaTenantConfig found for tenant_id={tenant_id}.")

    # 2. Load documents from database
    stmt_docs = (
        select(EtaDocument)
        .where(EtaDocument.tenant_id == tenant_id)
        .where(EtaDocument.internal_doc_id.in_(document_ids))
    )
    res_docs = await session.execute(stmt_docs)
    docs = list(res_docs.scalars().all())

    if not docs:
        raise EtaBatchSubmissionError("No matching documents found for batch submission.")

    # Verify all documents are in SIGNED state
    for doc in docs:
        if doc.state != EtaDocumentState.SIGNED:
            raise EtaBatchSubmissionError(
                f"Document '{doc.internal_doc_id}' is in state {doc.state}, "
                f"expected SIGNED before submission."
            )

    # 3. Build batch submission JSON payload (FR-535)
    submission_payload: dict[str, Any] = {
        "documents": [doc.payload_json for doc in docs]
    }

    eta_gateway = gateway or EtaGateway()

    # 4. Invoke ETA API with F-4 External Idempotency Timeout Protection
    try:
        response_data = await eta_gateway.submit_documents(
            tenant_config=tenant_config,
            submission_payload=submission_payload,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException, EtaTimeoutError) as exc:
        # F-4: TIMEOUT HANDLING - Do NOT blindly retry!
        uncertain_submission_id = f"UNCERTAIN-{uuid4().hex[:12].upper()}"
        submission = EtaSubmission(
            tenant_id=tenant_id,
            submission_uuid=uncertain_submission_id,
            document_ids=[doc.internal_doc_id for doc in docs],
            document_count=len(docs),
            response_status=408,  # Request Timeout
            submitted_at=datetime.now(UTC),
        )
        session.add(submission)

        for doc in docs:
            doc.state = EtaDocumentState.SUBMIT_UNCERTAIN
            doc.submission_uuid = uncertain_submission_id
            doc.next_attempt_at = None  # Prevent blind automatic retry
            session.add(doc)

        await session.commit()
        raise EtaSubmissionTimeoutError(
            "ETA API batch submission timed out (F-4). "
            "Documents transitioned to SUBMIT_UNCERTAIN state to prevent duplicate submissions."
        ) from exc

    # 5. Successful submission (HTTP 202 Accepted)
    submission_uuid = response_data.get("submissionId", f"SUB-{uuid4().hex[:12].upper()}")
    submission = EtaSubmission(
        tenant_id=tenant_id,
        submission_uuid=submission_uuid,
        document_ids=[doc.internal_doc_id for doc in docs],
        document_count=len(docs),
        response_status=202,
        submitted_at=datetime.now(UTC),
    )
    session.add(submission)

    for doc in docs:
        doc.state = EtaDocumentState.SUBMITTED
        doc.submission_uuid = submission_uuid
        doc.submitted_at = datetime.now(UTC)
        session.add(doc)

    await session.commit()
    return submission
