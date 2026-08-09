"""
app/modules/finance/api/settlements.py — COD Settlement Reconciliation & GL Posting Endpoints (FR-770 to FR-780)

Implements:
  - POST /api/v1/finance/settlements/upload
  - POST /api/v1/finance/settlements/match-json
  - POST /api/v1/finance/settlements/{settlement_id}/commit
  - GET  /api/v1/finance/settlements/aging/{carrier_code}
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.system.dependencies import CurrentUser
from app.modules.finance.models.settlements import (
    CarrierReceivableSnapshot,
    CarrierSettlement,
    CarrierSettlementState,
)
from app.modules.finance.services.matching import (
    SettlementFileParseError,
    generate_carrier_receivable_snapshot,
    match_settlement,
    parse_settlement_file,
)
from app.modules.finance.services.posting import (
    SettlementPostingError,
    post_settlement_to_gl,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/finance/settlements", tags=["COD Settlements"])


class SettlementMatchJsonRequest(BaseModel):
    carrier_code: str = Field(..., example="bosta")
    settlement_ref: str = Field(..., example="SET-2026-001")
    lines: list[dict[str, Any]] = Field(default_factory=list)
    tolerance: Decimal = Field(default=Decimal("5.0000"))
    date_window_days: int = Field(default=7)


@router.get(
    "",
    response_model=list[CarrierSettlement],
    summary="List carrier COD settlements",
)
async def list_settlements(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    carrier_code: str | None = Query(default=None),
    state: CarrierSettlementState | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CarrierSettlement]:
    """Lists all uploaded/matched carrier settlements for this tenant."""
    q = select(CarrierSettlement)
    if carrier_code:
        q = q.where(CarrierSettlement.carrier_code == carrier_code)
    if state:
        q = q.where(CarrierSettlement.state == state)
    q = q.order_by(CarrierSettlement.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return list(result.scalars().all())


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=CarrierSettlement,
    summary="Upload and Match Carrier Settlement Statement (FR-771, FR-772, FR-774)",
)
async def upload_settlement(
    current_user: CurrentUser,
    file: UploadFile = File(...),
    carrier_code: str = Form(...),
    settlement_ref: str = Form(...),
    tolerance: Decimal = Form(default=Decimal("5.0000")),
    date_window_days: int = Form(default=7),
    session: AsyncSession = Depends(get_tenant_db),
) -> CarrierSettlement:
    """
    Upload a carrier COD statement (CSV or JSON) and execute matching:
      - Exact AWB Matching (FR-771)
      - Fuzzy Matching on Amount + Date Window + Phone Tail (FR-772)
      - Exception Queue Classification (FR-774)
    """
    content = await file.read()
    filename = file.filename or "settlement.csv"

    try:
        lines = parse_settlement_file(content, filename)
    except SettlementFileParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        settlement = await match_settlement(
            session=session,
            carrier_code=carrier_code,
            settlement_ref=settlement_ref,
            lines=lines,
            tolerance=tolerance,
            date_window_days=date_window_days,
        )
        await session.commit()
        await session.refresh(settlement)
        return settlement
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to match uploaded COD settlement: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to match settlement: {exc}",
        ) from exc


@router.post(
    "/match-json",
    status_code=status.HTTP_201_CREATED,
    response_model=CarrierSettlement,
    summary="Match COD Settlement from JSON Payload (FR-771, FR-772)",
)
async def match_settlement_json(
    body: SettlementMatchJsonRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> CarrierSettlement:
    """
    JSON API alternative to multipart upload for reconciling settlement statement lines.
    """
    try:
        settlement = await match_settlement(
            session=session,
            carrier_code=body.carrier_code,
            settlement_ref=body.settlement_ref,
            lines=body.lines,
            tolerance=body.tolerance,
            date_window_days=body.date_window_days,
        )
        await session.commit()
        await session.refresh(settlement)
        return settlement
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to match JSON COD settlement: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to match JSON settlement: {exc}",
        ) from exc


@router.post(
    "/{settlement_id}/commit",
    status_code=status.HTTP_200_OK,
    summary="Post Reconciled COD Settlement to GL (FR-770, FR-773)",
)
async def commit_settlement_to_gl(
    settlement_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> dict[str, Any]:
    """
    Post a MATCHED or PARTIALLY_MATCHED settlement to the general ledger (FR-770, FR-773).
    Creates a balanced multi-line JournalEntry and updates settlement status.
    """
    try:
        journal_entry = await post_settlement_to_gl(
            session=session,
            settlement_id=settlement_id,
        )
        await session.commit()
        return {
            "status": "posted",
            "settlement_id": str(settlement_id),
            "journal_entry_id": str(journal_entry.id),
        }
    except SettlementPostingError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to post settlement %s to GL: %s", settlement_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error posting settlement: {exc}",
        ) from exc


@router.get(
    "/aging/{carrier_code}",
    status_code=status.HTTP_200_OK,
    response_model=CarrierReceivableSnapshot,
    summary="Get Outstanding Carrier COD Receivable Aging (FR-775)",
)
async def get_carrier_aging_snapshot(
    carrier_code: str,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> CarrierReceivableSnapshot:
    """
    Generate and return an aging analysis snapshot (0-7, 8-14, 15-30, 30+ days)
    for all DELIVERED COD shipments for a carrier that remain unsettled (FR-775).
    """
    try:
        snapshot = await generate_carrier_receivable_snapshot(
            session=session,
            carrier_code=carrier_code,
        )
        await session.commit()
        await session.refresh(snapshot)
        return snapshot
    except Exception as exc:
        await session.rollback()
        logger.exception("Failed to generate carrier receivable aging snapshot: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate aging snapshot: {exc}",
        ) from exc
