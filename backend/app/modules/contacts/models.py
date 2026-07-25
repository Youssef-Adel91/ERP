"""
app/modules/contacts/models.py — CRM Contact Model (Tenant Schema)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEO4J GRAPH MIGRATION NOTES (Future Sprint — Trust Network)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEO4J_NODE_LABEL:       Contact
# NEO4J_NODE_ID:           id
# NEO4J_NATURAL_KEY:       phone  ← deduplication key across tenants
# NEO4J_EXPORT_FIELDS:     [id, contact_type, name, phone, cod_risk_score]
#
# Extraction query (runs nightly via Celery):
#   SELECT id, contact_type, name, phone, cod_risk_score FROM contacts;
#   → MERGE (c:Contact {phone: row.phone})
#     ON CREATE SET c.id = row.id, c.name = row.name, c.type = row.contact_type
#     ON MATCH  SET c.cod_risk_score = row.cod_risk_score
#
# GRAPH EDGES (future ContactRelationship table → Neo4j):
#   (:Contact)-[:TRADED_WITH {count, total_value, cod_rejection_rate}]->(:Contact)
#   (:Contact)-[:SUPPLIED_BY]->(:Contact)
#
# COD RISK SCORE:
#   0.000 → 0.300  Safe     (accept COD)
#   0.301 → 0.699  Moderate (flag for review)
#   0.700 → 1.000  High     (reject COD / require prepayment)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Numeric, UniqueConstraint, text
from sqlmodel import Column, Field, Relationship, SQLModel


class ContactType(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"


class ContactStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


# ── Contact ───────────────────────────────────────────────────────────────────


class Contact(SQLModel, table=True):
    """
    Unified entity for Customers and Suppliers.

    A single contact can be BOTH a customer and a supplier
    (e.g. a distributor who buys from you and supplies to you).
    contact_type reflects the PRIMARY relationship.

    Trust Network Integration:
      cod_risk_score is updated by the COD Risk Assessment Plugin whenever:
      - A COD delivery is confirmed (score decreases)
      - A COD delivery is rejected (score increases)
      The score feeds directly into shipping decisions (see shipping plugin).
    """

    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_type", "contact_type"),
        Index("ix_contacts_status", "status"),
        CheckConstraint(
            "cod_risk_score >= 0.000 AND cod_risk_score <= 1.000",
            name="ck_contacts_risk_score_range",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    contact_type: ContactType
    status: ContactStatus = Field(default=ContactStatus.ACTIVE)

    # Identity
    name: str = Field(max_length=255, index=True)
    name_ar: str | None = Field(default=None, max_length=255)

    # Contact info
    phone: str | None = Field(default=None, max_length=20, index=True)
    phone_alt: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)

    # National ID — used for KYC and Neo4j cross-tenant deduplication
    national_id: str | None = Field(default=None, max_length=20)

    # ── Trust Network / COD Risk Fields ───────────────────────────────────────
    # NEO4J_PROPERTY: cod_risk_score
    # Updated by: COD Risk Assessment Plugin (shipping plugin events)
    cod_risk_score: Decimal = Field(
        default=Decimal("0.000"),
        sa_column=Column(Numeric(4, 3), nullable=False, server_default=text("0.000")),
    )
    cod_rejection_count: int = Field(default=0)
    cod_acceptance_count: int = Field(default=0)

    # Audit
    created_by: UUID | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": text("now()")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc).replace(tzinfo=None)},
    )

    # Relationship to Invoices (back-populated from inventory plugin)
    # Invoice.contact_id is a UUID FK → contacts.id
    invoices: list["Invoice"] = Relationship(  # noqa: F821 — forward ref to inventory
        back_populates="contact",
        sa_relationship_kwargs={"lazy": "select"},
    )
