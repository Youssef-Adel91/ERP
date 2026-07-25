"""
app/modules/news/router.py — Internal News/Announcements API
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_tenant_db
from app.core.security import RequireRole
from app.modules.system.dependencies import CurrentUser
from app.modules.news.models import Announcement
from app.modules.news.schemas import AnnouncementCreate, AnnouncementResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/",
    response_model=list[AnnouncementResponse],
    summary="List all announcements",
    tags=["Core / News"],
)
async def list_announcements(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> list[AnnouncementResponse]:
    """
    Returns all announcements for the current tenant, ordered by newest first.
    Accessible by ALL authenticated roles.
    """
    result = await db.execute(
        select(Announcement).order_by(Announcement.created_at.desc())
    )
    announcements = result.scalars().all()
    return [AnnouncementResponse.model_validate(a) for a in announcements]


@router.post(
    "/",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new announcement",
    dependencies=[Depends(RequireRole(["OWNER"]))],
    tags=["Core / News"],
)
async def create_announcement(
    data: AnnouncementCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AnnouncementResponse:
    """
    Create a new announcement. Only the OWNER can perform this action.
    """
    announcement = Announcement(
        title=data.title,
        content=data.content,
        created_by=current_user.id,
    )
    
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)

    return AnnouncementResponse.model_validate(announcement)
