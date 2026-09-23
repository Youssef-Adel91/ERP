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
    # Same naive-datetime bug already fixed for User.last_login_at (see
    # app/modules/system/router.py) -- this field has no explicit sa_type,
    # so it falls back to the project's default strict tz-aware datetime
    # column type. Fixed live, 2026-09-23.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"server_default": text("now()")},
    )
