"""
app/modules/news/models.py — Internal News / Announcements ORM Model (Tenant Schema)
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Field, SQLModel


class Announcement(SQLModel, table=True):
    """An internal announcement broadcast to all users of a tenant."""

    __tablename__ = "announcements"
    __table_args__ = ({"schema": "tenant"},)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(max_length=255)
    content: str

    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )
