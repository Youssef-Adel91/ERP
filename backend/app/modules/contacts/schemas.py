"""
app/modules/contacts/schemas.py — Contacts API Pydantic Schemas
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.contacts.models import ContactStatus, ContactType


class ContactCreateRequest(BaseModel):
    contact_type: ContactType
    name: str = Field(min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    phone_alt: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    national_id: str | None = Field(default=None, max_length=20)


class ContactUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    name_ar: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    status: ContactStatus | None = None


class ContactResponse(BaseModel):
    id: UUID
    contact_type: ContactType
    status: ContactStatus
    name: str
    name_ar: str | None
    phone: str | None
    email: str | None
    national_id: str | None
    cod_risk_score: Decimal
    cod_rejection_count: int
    cod_acceptance_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    total: int
    items: list[ContactResponse]
