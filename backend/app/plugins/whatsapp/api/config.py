"""
app/plugins/whatsapp/api/config.py — Per-Tenant WhatsApp Config CRUD

WhatsAppTenantConfig now lives in the public schema (see its module
docstring — required for the inbound webhook's phone_number_id ->
tenant_id resolution). This router therefore uses get_public_db instead
of get_tenant_db, but every query is still explicitly scoped by
current_user.tenant_id — a tenant can only ever see/edit its own row,
public-schema placement is a storage/lookup necessity, not a widening of
access.

WhatsAppClient (outbound) and api/webhooks.py (inbound) both now read
from here for real per-tenant credential resolution — see those modules.

Not gated by app.core.dependencies.plugin_gate.require_plugin("whatsapp")
deliberately: a tenant should be able to configure credentials BEFORE
flipping the Marketplace toggle on (setup naturally precedes activation),
same as ETA's config endpoint isn't gated by anything either.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_public_db
from app.modules.system.dependencies import CurrentUser
from app.plugins.whatsapp.models import WhatsAppTenantConfig

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Integration"])


class WhatsAppConfigIn(BaseModel):
    phone_number_id: str
    access_token_ref: str | None = None
    webhook_verify_token: str | None = None
    is_active: bool = False


@router.get("/config", response_model=WhatsAppTenantConfig | None)
async def get_config(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    result = await session.execute(
        select(WhatsAppTenantConfig).where(WhatsAppTenantConfig.tenant_id == current_user.tenant_id)
    )
    return result.scalar_one_or_none()


@router.put("/config", response_model=WhatsAppTenantConfig)
async def upsert_config(
    data: WhatsAppConfigIn,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_public_db),
):
    """Create or update this tenant's WhatsApp Business API configuration."""
    result = await session.execute(
        select(WhatsAppTenantConfig).where(WhatsAppTenantConfig.tenant_id == current_user.tenant_id)
    )
    config = result.scalar_one_or_none()
    if config:
        for field, value in data.model_dump().items():
            setattr(config, field, value)
    else:
        config = WhatsAppTenantConfig(tenant_id=current_user.tenant_id, **data.model_dump())
        session.add(config)
    try:
        await session.commit()
    except IntegrityError:
        # phone_number_id is globally unique — it's the reverse-lookup key
        # inbound webhooks use to resolve tenant_id, so two tenants can
        # never register the same Meta phone number.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="رقم الهاتف هذا (Phone Number ID) مُسجَّل بالفعل لدى مستأجر آخر.",
        )
    await session.refresh(config)
    return config
