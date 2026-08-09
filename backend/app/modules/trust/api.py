"""
app/modules/trust/api.py — Trust Network REST API (Phase 7a)

Exposes the cross-tenant, privacy-preserving reputation engine
(app.modules.trust.services.*). Runs against the `public` schema — this is
a global network shared across all tenants, not a per-tenant table — so
every endpoint uses `get_public_db`, not `get_tenant_db`.

Enforced by the underlying services, not re-implemented here:
  - PDPL privacy: queries never return or accept plaintext phone numbers;
    raw numbers are hashed with HMAC-SHA256 + a Vault-managed pepper before
    ever touching a query or being persisted.
  - Reciprocity Gate (FR-712): a tenant must have contributed to the network
    in the trailing 30 days before it may query scores.
  - K-Anonymity Gate: any phone hash backed by fewer than 3 distinct
    contributing tenants is masked as UNKNOWN, never returned as a real band.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.modules.system.dependencies import CurrentUser, require_roles
from app.modules.trust.models.core import ShipmentOutcome
from app.modules.trust.services.disputes import flag_contribution_as_disputed
from app.modules.trust.services.erasure import execute_data_subject_erasure
from app.modules.trust.services.gates import query_reputation
from app.modules.trust.services.hashing import get_vault_pepper, hash_phone_number
from app.modules.trust.services.pepper_rotation import rotate_pepper_job
from app.modules.trust.services.scoring import record_contribution

router = APIRouter(prefix="/trust", tags=["Trust Network"])


# ── Query reputation (read) ───────────────────────────────────────────────────


class ReputationQueryIn(BaseModel):
    phone: str


class ReputationOut(BaseModel):
    band: str
    explanation: str
    distinct_tenant_count: int


@router.post("/reputation/query", response_model=ReputationOut)
async def query_reputation_endpoint(
    data: ReputationQueryIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Look up a phone number's cross-tenant risk band. Enforces the
    Reciprocity Gate (403 if this tenant hasn't contributed recently) and
    the K-Anonymity Gate (masks to UNKNOWN below 3 distinct contributors).
    Never returns raw contribution data — categorical band only.
    """
    try:
        return await query_reputation(session, str(current_user.tenant_id), data.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# ── Contribute an outcome (write) ─────────────────────────────────────────────


class ContributionIn(BaseModel):
    phone: str
    outcome: ShipmentOutcome
    weight: Decimal = Decimal("1.0000")


@router.post("/contributions", status_code=status.HTTP_201_CREATED)
async def contribute_outcome(
    data: ContributionIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Report a shipment outcome (delivered/returned/refused) for a phone
    number. The raw phone number is hashed before it ever reaches the
    database or this function's return value — never stored in plaintext.
    """
    phone_hash = hash_phone_number(data.phone, pepper=get_vault_pepper())
    await record_contribution(
        session=session,
        phone_hash=phone_hash,
        tenant_id=str(current_user.tenant_id),
        outcome=data.outcome,
        weight=data.weight,
    )
    await session.commit()
    return {"status": "recorded"}


# ── Disputes ───────────────────────────────────────────────────────────────────


@router.post("/contributions/{id}/dispute")
async def dispute_contribution(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """
    Flag a contribution as disputed. Disputed contributions are excluded
    from the reputation recalculation (mathematically, not just hidden).
    """
    try:
        voided = await flag_contribution_as_disputed(session, id)
        await session.commit()
        return {"disputed": voided}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── PDPL Data-Subject Erasure (Egyptian Law 151/2020, "right to be forgotten") ──


class ErasureRequestIn(BaseModel):
    phone: str


class ErasureResultOut(BaseModel):
    erased: bool


@router.post(
    "/erasure",
    response_model=ErasureResultOut,
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def erase_data_subject(
    data: ErasureRequestIn,
    session: AsyncSession = Depends(get_public_db),
):
    """
    PDPL (Law 151/2020) right-to-erasure endpoint. Hard-deletes every trace of
    a phone number from the cross-tenant Trust Network (GlobalReputation +
    TrustContribution) — never a soft delete, as PDPL requires actual erasure.

    Gated to OWNER/ADMIN: this is a compliance operation triggered on behalf
    of a verified data-subject request (e.g. via a support/legal workflow),
    not a self-service consumer-facing action. Building a customer-facing,
    OTP-verified request channel (FR-722/723) is a separate, not-yet-built
    surface; this endpoint is the enforcement primitive it would call into.
    Whether/when the network processes real consumer data in production is
    a legal/management decision, not a code gate — this endpoint is correct
    and safe to have live regardless of that decision.
    """
    erased = await execute_data_subject_erasure(session, data.phone)
    await session.commit()
    return ErasureResultOut(erased=erased)


# ── Pepper rotation (internal key-management operation) ───────────────────────


class PepperRotationIn(BaseModel):
    old_pepper: str
    new_pepper: str
    new_version: int


@router.post(
    "/admin/rotate-pepper",
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def rotate_pepper(data: PepperRotationIn):
    """
    Triggers a full Trust Network pepper (HMAC key) rotation: re-hashes every
    tenant's contact phone numbers under the new pepper and migrates
    GlobalReputation/TrustContribution rows to the new hash. This is a slow,
    all-tenant background operation — intended for internal/ops use (e.g. a
    scheduled key-rotation runbook), not routine merchant-facing usage.
    Vault-held pepper values must be supplied explicitly; this endpoint does
    not fetch or guess them.
    """
    return await rotate_pepper_job(data.old_pepper, data.new_pepper, data.new_version)
