"""
app.modules.eta.models.codes — Item Coding Registry for ETA Compliance (Phase 5 - Step 3)

Defines:
  1. EgsCode: mapping ERP items/variants to EGS (Egyptian Goods & Services) or GS1 codes (FR-520).
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.db.base import TenantBase


class EgsCodeType(StrEnum):
    EGS = "EGS"
    GS1 = "GS1"


class EgsCode(TenantBase, table=True):
    """
    Item Coding Registry (FR-520, FR-521).
    Every invoice item MUST map to an active EgsCode before canonical serialization and ETA submission.
    """
    __tablename__ = "egs_codes"
    __table_args__ = (
        UniqueConstraint("item_id", "variant_id", "code_type", name="uq_egs_codes_item_variant_type"),
        {"schema": "tenant"},
    )

    tenant_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    variant_id: UUID | None = Field(default=None, index=True)
    code_type: str = Field(default=EgsCodeType.EGS, max_length=10, index=True)
    code_value: str = Field(max_length=100, index=True)  # e.g., "EG-100200300-12345" or "06221234567890"
    parent_code: str | None = Field(default=None, max_length=100)  # e.g., GPC Brick code "10000000"
    name_ar: str | None = Field(default=None, max_length=255)
    name_en: str | None = Field(default=None, max_length=255)
    status: str = Field(default="Approved", max_length=30)
    is_active: bool = Field(default=True, index=True)
