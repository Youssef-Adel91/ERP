"""
app/modules/core/models.py — Core/Shared Models (Tenant Schema)
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, func
from sqlmodel import Field

from app.core.db.base import TenantBase


class Branch(TenantBase, table=True):
    __tablename__ = "branches"
    __table_args__ = ({"schema": "tenant", "extend_existing": True},)
    name: str = Field(max_length=255, index=True)
    code: str = Field(max_length=50, index=True)
    is_active: bool = Field(default=True)


class Attachment(TenantBase, table=True):
    __tablename__ = "attachments"
    __table_args__ = ({"schema": "tenant", "extend_existing": True},)
    file_path: str = Field(max_length=1000)
    file_size: int = Field(default=0)
    mime_type: str = Field(max_length=100)


class DocumentSequence(TenantBase, table=True):
    __tablename__ = "document_sequences"
    __table_args__ = ({"schema": "tenant", "extend_existing": True},)
    prefix: str = Field(max_length=20)
    current_value: int = Field(default=0)
    document_type: str = Field(max_length=50, index=True)


class AuditLog(TenantBase, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = ({"schema": "tenant", "extend_existing": True},)
    action: str = Field(max_length=100)
    target_id: UUID | None = Field(default=None)
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, default=dict, nullable=False))


class ProcessedEvent(TenantBase, table=True):
    """Tracks processed events to guarantee idempotency in consumers."""
    __tablename__ = "processed_events"
    __table_args__ = ({"schema": "tenant", "extend_existing": True},)

    consumer_name: str = Field(max_length=100, primary_key=True)
    event_id: UUID = Field(primary_key=True)
    processed_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
