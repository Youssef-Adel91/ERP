"""
app/modules/eta/api/config.py — ETA Compliance REST API: config, EGS registry,
document state (read/manage)

Note (historical, resolved): this router originally excluded the submission
pipeline because build_eta_invoice()/submit_eta_batch() import
`app.modules.sales.models.invoice.SalesInvoice` and
`app.modules.inventory.models.core.Item`, which were dormant/unprovisioned
tables while the plugins/-vs-modules/ Inventory/Sales/Purchasing conflict was
unresolved. That cutover is now complete — modules/ is the live
implementation with provisioned tables and a working API — so the submission
endpoint is now wired too, in api/submissions.py (POST
/eta/submissions/invoice/{invoice_id}).

This file still covers only the config/registry/read surface:
  - EtaTenantConfig CRUD (per-tenant e-invoicing credentials/settings)
  - EgsCode registry CRUD (item → EGS/GS1 code mapping)
  - EtaDocument read endpoints (list/get existing submission state)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.eta.models.codes import EgsCode, EgsCodeType
from app.modules.eta.models.core import (
    EtaDocument,
    EtaDocumentState,
    EtaEnvironment,
    EtaSigningProvider,
    EtaTenantConfig,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/eta", tags=["ETA E-Invoicing"])


# ── Tenant Configuration ──────────────────────────────────────────────────────


class EtaTenantConfigIn(BaseModel):
    environment: EtaEnvironment = EtaEnvironment.PREPRODUCTION
    client_id: str
    client_secret_ref: str | None = None
    taxpayer_rin: str
    activity_code: str
    branch_eta_codes: dict[str, str] = {}
    signing_provider: EtaSigningProvider = EtaSigningProvider.CLOUD_HSM


@router.get("/config", response_model=EtaTenantConfig | None)
async def get_config(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    result = await session.execute(
        select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == current_user.tenant_id)
    )
    return result.scalar_one_or_none()


@router.put("/config", response_model=EtaTenantConfig)
async def upsert_config(
    data: EtaTenantConfigIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    """Create or update this tenant's ETA configuration (owner/admin only in practice)."""
    result = await session.execute(
        select(EtaTenantConfig).where(EtaTenantConfig.tenant_id == current_user.tenant_id)
    )
    config = result.scalar_one_or_none()
    if config:
        for field, value in data.model_dump().items():
            setattr(config, field, value)
    else:
        config = EtaTenantConfig(tenant_id=current_user.tenant_id, **data.model_dump())
        session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


# ── EGS/GS1 Item Code Registry ────────────────────────────────────────────────


class EgsCodeIn(BaseModel):
    item_id: UUID
    variant_id: UUID | None = None
    code_type: EgsCodeType = EgsCodeType.EGS
    code_value: str
    parent_code: str | None = None
    name_ar: str | None = None
    name_en: str | None = None


@router.post("/egs-codes", response_model=EgsCode, status_code=status.HTTP_201_CREATED)
async def create_egs_code(
    data: EgsCodeIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    code = EgsCode(tenant_id=current_user.tenant_id, **data.model_dump())
    session.add(code)
    await session.commit()
    await session.refresh(code)
    return code


@router.get("/egs-codes", response_model=list[EgsCode])
async def list_egs_codes(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    item_id: UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    q = select(EgsCode)
    if item_id:
        q = q.where(EgsCode.item_id == item_id)
    if is_active is not None:
        q = q.where(EgsCode.is_active == is_active)
    result = await session.execute(q)
    return result.scalars().all()


# ── Document Submission State (read-only) ────────────────────────────────────


@router.get("/documents", response_model=list[EtaDocument])
async def list_documents(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    state: EtaDocumentState | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(EtaDocument).where(EtaDocument.tenant_id == current_user.tenant_id)
    if state:
        q = q.where(EtaDocument.state == state)
    q = q.order_by(EtaDocument.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/documents/{id}", response_model=EtaDocument)
async def get_document(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    doc = await session.get(EtaDocument, id)
    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="ETA document not found.")
    return doc
