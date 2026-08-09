"""
app/modules/inventory/api/serial_lifecycle.py — Serial Number Lifecycle API

Exposes app/modules/inventory/services/serial_lifecycle.py's
transition_serial_state (state-machine transitions for SerialNumber) and
validate_sales_return (FR-345 return-fraud check: the serial must be SOLD
and previously sold to the exact contact attempting the return) as thin
HTTP endpoints.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.inventory.models.core import SerialNumber, SerialState
from app.modules.inventory.services.serial_lifecycle import (
    IllegalStateException,
    transition_serial_state,
    validate_sales_return,
)
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/inventory/serials", tags=["Inventory - Serial Lifecycle"])


class SerialTransitionRequest(BaseModel):
    new_state: SerialState
    contact_id: UUID | None = None


@router.post(
    "/{serial_id}/transition",
    response_model=SerialNumber,
    summary="Transition a serial number to a new state (validated against the allowed state machine)",
)
async def transition_serial(
    serial_id: UUID,
    data: SerialTransitionRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> SerialNumber:
    try:
        serial = await transition_serial_state(
            session=session,
            serial_id=serial_id,
            new_state=data.new_state,
            contact_id=data.contact_id,
        )
        await session.commit()
        await session.refresh(serial)
        return serial
    except IllegalStateException as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


class ValidateSalesReturnRequest(BaseModel):
    serial_id: UUID
    returning_contact_id: UUID


class ValidateSalesReturnResponse(BaseModel):
    valid: bool


@router.post(
    "/validate-return",
    response_model=ValidateSalesReturnResponse,
    summary="Validate a sales return against a serial number (FR-345 return-fraud check)",
)
async def validate_return(
    data: ValidateSalesReturnRequest,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
) -> ValidateSalesReturnResponse:
    try:
        ok = await validate_sales_return(
            session=session,
            serial_id=data.serial_id,
            returning_contact_id=data.returning_contact_id,
        )
    except ValueError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from exc

    return ValidateSalesReturnResponse(valid=ok)
