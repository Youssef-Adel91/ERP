"""
app/modules/eta/api/submissions.py — ETA Submission Pipeline (Phase 5, unblocked)

Previously deliberately NOT exposed (see api/config.py's module docstring):
services/builder.py hard-imports app.modules.sales.models.invoice.SalesInvoice
and app.modules.inventory.models.core.Item, which were dormant/unprovisioned
tables under the plugins/-vs-modules/ conflict. Now that the Inventory/Sales/
Purchasing cutover is complete — modules/ is the live implementation, its
tables are provisioned, and a real API sits in front of them — this endpoint
is safe to wire.

Full pipeline per invoice, all inside one endpoint:
  1. Load this tenant's EtaTenantConfig (must exist — set up via PUT /eta/config
     first).
  2. build_eta_invoice() + canonicalize + hash + sign
     (services.builder.prepare_signed_eta_document) — enforces the FR-521
     pre-submission gate (every line must resolve to an active EGS/GS1 code
     in the EgsCode registry or Item.egs_code; raises EtaMissingItemCodeError
     otherwise, surfaced as 422 so the merchant can fix data before ever
     hitting ETA).
  3. Persist the resulting EtaDocument (state=SIGNED).
  4. services.submission.submit_eta_batch() — the real HTTP call to the ETA
     gateway (id.preprod.eta.gov.eg / api.preprod.eta.gov.eg by default,
     PRODUCTION only if the tenant's EtaTenantConfig.environment is
     explicitly set to PRODUCTION with real credentials). Implements F-4
     external-idempotency: a network timeout transitions the document to
     SUBMIT_UNCERTAIN rather than blindly retrying (would risk duplicate
     submission), and this endpoint reports that back as 202 Accepted with
     the uncertain document state, not a hard error — the merchant must
     verify via GET /eta/documents/{id} or the callback webhook before
     deciding whether to resubmit.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.eta.exceptions import (
    EtaAuthenticationError,
    EtaMissingItemCodeError,
    EtaRateDeferredError,
    EtaServiceUnavailableError,
    EtaSubmissionTimeoutError,
)
from app.modules.eta.models.core import EtaDocument, EtaTenantConfig
from app.modules.eta.services.builder import prepare_signed_eta_document
from app.modules.eta.services.submission import submit_eta_batch
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/eta/submissions", tags=["ETA E-Invoicing"])


@router.post(
    "/invoice/{invoice_id}",
    response_model=EtaDocument,
    summary="Build, sign, and submit a SalesInvoice to the Egyptian Tax Authority",
)
async def submit_invoice_to_eta(
    invoice_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> EtaDocument:
    # 1. Tenant must have configured ETA credentials first.
    cfg_stmt = select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == current_user.tenant_id)
    tenant_config = (await session.execute(cfg_stmt)).scalar_one_or_none()
    if not tenant_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ETA is not configured for this tenant. Set up credentials via PUT /eta/config first.",
        )

    # 2 + 3. Build ETA JSON, canonicalize, hash, sign, persist as SIGNED.
    try:
        eta_doc = await prepare_signed_eta_document(session, invoice_id, tenant_config)
    except EtaMissingItemCodeError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    session.add(eta_doc)
    await session.commit()
    await session.refresh(eta_doc)

    # 4. Submit the signed document to the real ETA gateway.
    try:
        await submit_eta_batch(
            session=session,
            tenant_id=tenant_config.tenant_id,
            document_ids=[eta_doc.internal_doc_id],
        )
    except EtaSubmissionTimeoutError:
        # F-4: document already transitioned to SUBMIT_UNCERTAIN and committed
        # by submit_eta_batch itself. Report as 202 — not a failure, but not
        # confirmed either; the merchant must check status before resubmitting.
        await session.refresh(eta_doc)
        return eta_doc
    except EtaAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ETA authentication failed — check the tenant's client_id/secret in /eta/config: {exc}",
        ) from exc
    except EtaRateDeferredError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except EtaServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    await session.refresh(eta_doc)
    return eta_doc
