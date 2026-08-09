"""
app.modules.logistics.api.carriers — Per-Tenant Carrier Account Configuration

Lets a tenant configure which carriers (Bosta, Mylerz) they use and store
credentials/webhook secrets by Vault reference — never a raw secret, same
convention as app.plugins.whatsapp.api.config and app.modules.eta.api.config
(the tenant pastes a `vault://...` reference string; the actual secret is
resolved at send/verify time by app.modules.logistics.services.vault).

GET /logistics/carriers/available (list of supported carrier codes) is
registered BEFORE GET/PUT /logistics/carriers/{account_id} so the literal
path isn't swallowed by the dynamic one (same route-ordering discipline
used throughout this project — see app.modules.cases.router's comments).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db.database import get_tenant_db
from app.modules.system.dependencies import CurrentUser
from app.modules.logistics.models.carriers import CarrierAccount
from app.modules.logistics.providers.registry import list_supported_carriers

router = APIRouter(prefix="/logistics/carriers", tags=["Logistics — Carrier Accounts"])

_CARRIER_LABELS: dict[str, str] = {
    "bosta": "بوسطة (Bosta)",
    "mylerz": "ميلرز (Mylerz)",
}


class CarrierAccountIn(BaseModel):
    carrier_code: str
    credentials_ref: str
    webhook_secret_ref: str
    is_active: bool = True


class CarrierAccountUpdate(BaseModel):
    credentials_ref: str | None = None
    webhook_secret_ref: str | None = None
    is_active: bool | None = None


@router.get("/available")
async def list_available_carriers() -> list[dict[str, str]]:
    """Supported carrier codes this platform knows how to integrate with."""
    return [
        {"code": code, "label": _CARRIER_LABELS.get(code, code)}
        for code in list_supported_carriers()
    ]


@router.get("", response_model=list[CarrierAccount])
async def list_carrier_accounts(current_user: CurrentUser, db=Depends(get_tenant_db)):
    result = await db.execute(select(CarrierAccount))
    return result.scalars().all()


@router.post("", response_model=CarrierAccount, status_code=status.HTTP_201_CREATED)
async def create_carrier_account(
    data: CarrierAccountIn,
    current_user: CurrentUser,
    db=Depends(get_tenant_db),
):
    code = data.carrier_code.lower().strip()
    if code not in list_supported_carriers():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"شركة الشحن '{data.carrier_code}' غير مدعومة حاليًا.",
        )
    account = CarrierAccount(
        carrier_code=code,
        credentials_ref=data.credentials_ref,
        webhook_secret_ref=data.webhook_secret_ref,
        is_active=data.is_active,
    )
    db.add(account)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="حساب شركة الشحن هذه مُعدّ بالفعل — استخدم التعديل بدلًا من الإضافة.",
        )
    await db.refresh(account)
    return account


@router.put("/{account_id}", response_model=CarrierAccount)
async def update_carrier_account(
    account_id: UUID,
    data: CarrierAccountUpdate,
    current_user: CurrentUser,
    db=Depends(get_tenant_db),
):
    account = await db.get(CarrierAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="حساب شركة الشحن غير موجود.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.commit()
    await db.refresh(account)
    return account
