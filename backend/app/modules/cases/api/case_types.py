"""
app/modules/cases/api/case_types.py — Case Type Configuration API

Was entirely missing: the case engine requires a `case_type_id` to open a
Case, but there was no endpoint to create or discover CaseType rows. Verticals
(recruitment/travel/hospitality/rental) seed their own via bootstrap
endpoints, but there was no generic way to list/create one — this closes
that gap for custom/manual case workflows.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import CaseType
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/case-types", tags=["Case Engine"])


class CaseTypeCreate(BaseModel):
    code: str
    name: str
    name_ar: str | None = None
    plugin_key: str = "custom"
    initial_stage: str
    stages: list[dict[str, Any]]


@router.post("", response_model=CaseType, status_code=201)
async def create_case_type(
    data: CaseTypeCreate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    case_type = CaseType(**data.model_dump(), created_by=current_user.id)
    session.add(case_type)
    await session.commit()
    await session.refresh(case_type)
    return case_type


@router.get("", response_model=list[CaseType])
async def list_case_types(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    plugin_key: str | None = None,
):
    q = select(CaseType)
    if plugin_key:
        q = q.where(CaseType.plugin_key == plugin_key)
    result = await session.execute(q.order_by(CaseType.name))
    return result.scalars().all()


@router.get("/{id}", response_model=CaseType)
async def get_case_type(
    id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    case_type = await session.get(CaseType, id)
    if not case_type:
        raise HTTPException(status_code=404, detail="Case type not found")
    return case_type
