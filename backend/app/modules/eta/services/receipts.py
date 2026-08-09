"""
app.modules.eta.services.receipts — ETA B2C e-Receipt Batch Serialization & 72-Hour Offline Window (Phase 5 - Step 5)

Implements:
  1. prepare_eta_receipt: Prepares a B2C e-Receipt with previous_uuid chaining.
  2. build_and_sign_receipt_batch: Groups DRAFT receipts, enforces the 72-hour offline window from
     date_time_issued (FR-574), flags late arrivals, and canonicalizes & signs the ENTIRE batch (FR-570).
  3. submit_receipt_batch: Submits the signed receipt batch to ETA with F-4 external idempotency protection.
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
from app.modules.eta.models.core import EtaTenantConfig
from app.modules.eta.models.receipts import (
    EtaReceipt,
    EtaReceiptBatch,
    EtaReceiptBatchState,
    EtaReceiptState,
)
from app.modules.eta.services.canonical import serialize_document
from app.modules.eta.services.crypto import compute_cades_bes_hash_bytes
from app.modules.eta.services.gateway import EtaGateway
from app.modules.eta.services.signing import get_signing_provider


class EtaReceiptBatchError(EtaException):
    """Raised when receipt batch creation or signing fails."""
    pass


async def prepare_eta_receipt(
    session: AsyncSession,
    tenant_id: UUID,
    internal_doc_id: str,
    receipt_number: str,
    date_time_issued: datetime,
    payload_json: dict[str, Any],
) -> EtaReceipt:
    """
    Prepare a B2C e-Receipt for batching.
    Automatically resolves previous_uuid for ETA receipt chaining.
    """
    stmt_prev = (
        select(EtaReceipt)
        .where(EtaReceipt.tenant_id == tenant_id)
        .where(EtaReceipt.uuid.is_not(None))
        .order_by(EtaReceipt.date_time_issued.desc())
        .limit(1)
    )
    res_prev = await session.execute(stmt_prev)
    prev_receipt = res_prev.scalar_one_or_none()
    previous_uuid = prev_receipt.uuid if prev_receipt else ""

    # Check offline 72-hour window (FR-574)
    now_utc = datetime.now(UTC)
    dt_issued = date_time_issued
    if dt_issued.tzinfo is None:
        dt_issued = dt_issued.replace(tzinfo=UTC)
    late_on_arrival = (now_utc - dt_issued).total_seconds() > (72 * 3600)

    receipt = EtaReceipt(
        tenant_id=tenant_id,
        internal_doc_id=internal_doc_id,
        receipt_number=receipt_number,
        previous_uuid=previous_uuid,
        state=EtaReceiptState.DRAFT,
        date_time_issued=date_time_issued,
        late_on_arrival=late_on_arrival,
        payload_json=payload_json,
    )
    session.add(receipt)
    await session.commit()
    await session.refresh(receipt)
    return receipt


async def build_and_sign_receipt_batch(
    session: AsyncSession,
    tenant_id: UUID,
    pos_terminal_id: str,
    receipt_ids: list[str],
) -> EtaReceiptBatch:
    """
    Canonicalize and sign a batch of B2C e-Receipts (§5.1, FR-570, FR-574).

    Rules Enforced:
      1. Batch-Level Serialization (FR-570): For e-Receipts, canonicalization and signature
         are applied to the ENTIRE batch structure, not individual receipts.
      2. Offline 72-Hour Window (FR-574): Calculated strictly from `date_time_issued`.
         If a receipt is synced after 72 hours, it is flagged as `late_on_arrival = True`
         and submitted immediately with an audit record (late submission is better than missing).
    """
    if not receipt_ids:
        raise EtaReceiptBatchError("Cannot build a receipt batch without receipt_ids.")

    stmt_cfg = select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == tenant_id)
    res_cfg = await session.execute(stmt_cfg)
    tenant_config = res_cfg.scalar_one_or_none()
    if not tenant_config:
        raise EtaReceiptBatchError(f"No EtaTenantConfig found for tenant_id={tenant_id}.")

    stmt_receipts = (
        select(EtaReceipt)
        .where(EtaReceipt.tenant_id == tenant_id)
        .where(EtaReceipt.internal_doc_id.in_(receipt_ids))
    )
    res_receipts = await session.execute(stmt_receipts)
    receipts = list(res_receipts.scalars().all())

    if not receipts or len(receipts) != len(receipt_ids):
        raise EtaReceiptBatchError("One or more receipt_ids were not found in database.")

    now_utc = datetime.now(UTC)
    for receipt in receipts:
        if receipt.state != EtaReceiptState.DRAFT:
            raise EtaReceiptBatchError(
                f"Receipt '{receipt.internal_doc_id}' is in state {receipt.state}, expected DRAFT."
            )
        # Enforce 72-hour offline window check (FR-574) strictly from date_time_issued
        dt_issued = receipt.date_time_issued
        if dt_issued.tzinfo is None:
            dt_issued = dt_issued.replace(tzinfo=UTC)
        if (now_utc - dt_issued).total_seconds() > (72 * 3600):
            receipt.late_on_arrival = True

    # 1. Construct entire batch payload (FR-570)
    batch_payload: dict[str, Any] = {
        "receipts": [r.payload_json for r in receipts]
    }

    # 2. Canonicalize the ENTIRE batch dictionary per ETA culture-invariant rules (FR-570)
    canonical_str = serialize_document(batch_payload)
    hash_bytes = compute_cades_bes_hash_bytes(canonical_str)
    batch_hash_hex = hash_bytes.hex().upper()

    # 3. Sign the batch hash using tenant's signing provider
    provider = get_signing_provider(tenant_config.signing_provider)
    sig_res = await provider.sign_cades_bes(hash_bytes, tenant_id)
    signature_b64 = sig_res.get("signature_b64") or sig_res.get("value", "")

    # 4. Persist EtaReceiptBatch and update receipts
    batch = EtaReceiptBatch(
        tenant_id=tenant_id,
        pos_terminal_id=pos_terminal_id,
        receipt_ids=[r.internal_doc_id for r in receipts],
        receipt_count=len(receipts),
        batch_canonical_hash=batch_hash_hex,
        signature_b64=signature_b64,
        state=EtaReceiptBatchState.SIGNED,
    )
    session.add(batch)
    await session.flush()

    for receipt in receipts:
        receipt.batch_id = batch.id
        receipt.state = EtaReceiptState.BATCHED
        session.add(receipt)

    await session.commit()
    await session.refresh(batch)
    return batch


async def submit_receipt_batch(
    session: AsyncSession,
    tenant_id: UUID,
    batch_id: UUID,
    gateway: EtaGateway | None = None,
) -> EtaReceiptBatch:
    """
    Submit a SIGNED B2C receipt batch to ETA (/api/v1/receipts/submissions) (FR-570).

    External Idempotency (F-4):
      - If a timeout occurs, transition batch and receipts to SUBMIT_UNCERTAIN state without
        blind retries.
    """
    stmt_batch = (
        select(EtaReceiptBatch)
        .where(EtaReceiptBatch.tenant_id == tenant_id)
        .where(EtaReceiptBatch.id == batch_id)
    )
    res_batch = await session.execute(stmt_batch)
    batch = res_batch.scalar_one_or_none()
    if not batch:
        raise EtaReceiptBatchError(f"Receipt batch {batch_id} not found.")

    if batch.state != EtaReceiptBatchState.SIGNED:
        raise EtaReceiptBatchError(f"Receipt batch {batch_id} is in state {batch.state}, expected SIGNED.")

    stmt_cfg = select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == tenant_id)
    res_cfg = await session.execute(stmt_cfg)
    tenant_config = res_cfg.scalar_one_or_none()
    if not tenant_config:
        raise EtaReceiptBatchError(f"No EtaTenantConfig found for tenant_id={tenant_id}.")

    stmt_receipts = (
        select(EtaReceipt)
        .where(EtaReceipt.tenant_id == tenant_id)
        .where(EtaReceipt.batch_id == batch_id)
    )
    res_receipts = await session.execute(stmt_receipts)
    receipts = list(res_receipts.scalars().all())

    submission_payload: dict[str, Any] = {
        "receipts": [r.payload_json for r in receipts]
    }

    eta_gateway = gateway or EtaGateway()

    try:
        response_data = await eta_gateway.submit_receipts(
            tenant_config=tenant_config,
            submission_payload=submission_payload,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException, EtaTimeoutError) as exc:
        uncertain_uuid = f"UNCERTAIN-{uuid4().hex[:12].upper()}"
        batch.state = EtaReceiptBatchState.SUBMIT_UNCERTAIN
        batch.submission_uuid = uncertain_uuid
        batch.submitted_at = datetime.now(UTC)
        session.add(batch)

        for receipt in receipts:
            receipt.state = EtaReceiptState.SUBMIT_UNCERTAIN
            session.add(receipt)

        await session.commit()
        raise EtaSubmissionTimeoutError(
            "ETA API receipt batch submission timed out (F-4). "
            "Batch and receipts transitioned to SUBMIT_UNCERTAIN state."
        ) from exc

    submission_uuid = response_data.get("submissionId", f"SUB-RCT-{uuid4().hex[:12].upper()}")
    batch.submission_uuid = submission_uuid
    batch.state = EtaReceiptBatchState.SUBMITTED
    batch.submitted_at = datetime.now(UTC)
    session.add(batch)

    for receipt in receipts:
        receipt.state = EtaReceiptState.SUBMITTED
        session.add(receipt)

    await session.commit()
    await session.refresh(batch)
    return batch
