"""
app/modules/contacts/models.py — CRM Contact Model (Tenant Schema)
"""

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Index, Numeric, text
from sqlmodel import Column, Field

from app.core.db.base import TenantBase


class ContactType(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"


class ContactStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class Contact(TenantBase, table=True):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_type", "contact_type"),
        Index("ix_contacts_status", "status"),
        CheckConstraint(
            "cod_risk_score >= 0.000 AND cod_risk_score <= 1.000",
            name="ck_contacts_risk_score_range",
        ),
        {"schema": "tenant"},
    )

    contact_type: ContactType = Field(sa_column=Column(sa.Enum(ContactType, name='contacttype', schema='tenant'), nullable=False))
    status: ContactStatus = Field(default=ContactStatus.ACTIVE, sa_column=Column(sa.Enum(ContactStatus, name='contactstatus', schema='tenant'), default=ContactStatus.ACTIVE, nullable=False))

    name: str = Field(max_length=255, index=True)
    name_ar: str | None = Field(default=None, max_length=255)

    phone: str | None = Field(default=None, max_length=20, index=True)
    phone_alt: str | None = Field(default=None, max_length=20)
    phone_e164: str | None = Field(default=None, max_length=20, index=True)
    email: str | None = Field(default=None, max_length=320)

    national_id: str | None = Field(default=None, max_length=20)
    branch_id: UUID | None = Field(default=None, index=True)

    cod_risk_score: Decimal = Field(
        default=Decimal("0.000"),
        sa_column=Column(Numeric(4, 3), nullable=False, server_default=text("0.000")),
    )
    cod_rejection_count: int = Field(default=0)
    cod_acceptance_count: int = Field(default=0)

    # NOTE: a `invoices: list["Invoice"] = Relationship(...)` attribute used
    # to live here, pointing at the now-retired app.plugins.inventory.models.
    # Invoice (see app.core.db.database's cutover comment — that whole
    # plugins.{inventory,sales,purchases} tree was replaced by
    # app.modules.{inventory,sales,purchasing}). That plugin module is no
    # longer imported anywhere, so the forward ref "Invoice" was a dangling
    # string reference. SQLAlchemy configures ALL mappers in the shared
    # registry on first query against ANY mapped class, so this wasn't a
    # dormant no-op — it 500'd every single query touching Contact
    # (`InvalidRequestError: ... 'Invoice' failed to locate a name`),
    # discovered while wiring the carrier webhook fix. Removed rather than
    # repointed at app.modules.sales.models.invoice.SalesInvoice, since that
    # side has no matching back_populates/relationship or FK constraint on
    # contact_id today — wiring that properly is a separate, deliberate
    # change, not a silent side effect of a bug fix.

