"""
app/modules/contacts/service.py — Contacts Business Logic
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import ContactCreatedEvent, get_event_bus
from app.modules.contacts.models import Contact, ContactRelationship, RelationshipType
from app.modules.contacts.schemas import (
    ContactCreateRequest,
    ContactRelationshipCreateRequest,
)

logger = logging.getLogger(__name__)


class ContactNotFoundError(LookupError):
    """Raised when a contact doesn't exist."""


async def create_contact(
    data: ContactCreateRequest,
    created_by: UUID,
    tenant_id: str,
    db: AsyncSession,
) -> Contact:
    """Create a new contact and emit ContactCreatedEvent."""
    contact = Contact(
        contact_type=data.contact_type,
        name=data.name,
        name_ar=data.name_ar,
        phone=data.phone,
        phone_alt=data.phone_alt,
        email=data.email,
        national_id=data.national_id,
        address=data.address,
        tags=data.tags,
        metadata=data.metadata,
        created_by=created_by,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    # Emit event for downstream systems (e.g. Trust Network pre-processing)
    event_bus = get_event_bus()
    await event_bus.publish(
        ContactCreatedEvent(
            tenant_id=tenant_id,
            payload={
                "contact_id": str(contact.id),
                "contact_type": contact.contact_type.value,
                "phone": contact.phone,
                # NEO4J_EXPORT_TRIGGER: This event triggers async node creation
            },
        )
    )

    logger.info("Created contact '%s' (type=%s)", contact.name, contact.contact_type)
    return contact


async def get_contacts(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> list[Contact]:
    """List all active contacts."""
    result = await db.execute(
        select(Contact)
        .order_by(Contact.name)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_contact_by_id(contact_id: UUID, db: AsyncSession) -> Contact:
    """Fetch contact by ID."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise ContactNotFoundError(f"Contact '{contact_id}' not found.")
    return contact


async def create_relationship(
    data: ContactRelationshipCreateRequest,
    db: AsyncSession,
) -> ContactRelationship:
    """Create a directed relationship between two contacts."""
    rel = ContactRelationship(
        source_contact_id=data.source_contact_id,
        target_contact_id=data.target_contact_id,
        relationship_type=data.relationship_type,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel
