"""
app/modules/news/schemas.py — News & Announcements Schemas
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=5)


class AnnouncementResponse(BaseModel):
    id: UUID
    title: str
    content: str
    created_by: UUID | None
    created_at: datetime

    class Config:
        from_attributes = True
