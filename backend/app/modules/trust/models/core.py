"""
app.modules.trust.models.core — Cross-Tenant Privacy Models (Phase 7a)

WARNING: STRICT PII PROHIBITION (Egyptian PDPL)
NO PLAINTEXT PHONE NUMBERS, EMAILS, OR NAMES MAY BE STORED IN THIS MODULE.
All keys must be HMAC-SHA256 hashed using the Vault PEPPER.
This schema operates globally across all tenants.
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, Numeric
from sqlmodel import Field, SQLModel


class TrustRiskBand(str, enum.Enum):
    UNKNOWN = "UNKNOWN"
    NEW = "NEW"
    GOOD = "GOOD"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"


class ShipmentOutcome(str, enum.Enum):
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"
    REFUSED = "REFUSED"


class GlobalReputation(SQLModel, table=True):
    """
    Aggregated cross-tenant reputation score for an anonymized phone hash.
    Schema: public (cross-tenant)
    """
    __tablename__ = "global_reputation"
    __table_args__ = {"schema": "public", "extend_existing": True}

    # Cryptographic hash (HMAC-SHA256) of E.164 phone number
    phone_hash: str = Field(primary_key=True, max_length=64)
    pepper_version: int = Field(default=1)

    # Core K-Anonymity Gate Metric
    distinct_tenant_count: int = Field(default=0)

    # Derived score
    recency_weighted_return_rate: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(10, 4), nullable=False)
    )
    band: TrustRiskBand = Field(default=TrustRiskBand.UNKNOWN)

    # NOTE (Phase F fix, 2026-09-11): the column has no timezone=True, so it
    # is a naive TIMESTAMP WITHOUT TIME ZONE — a tz-aware default_factory
    # value made every INSERT/UPDATE fail with asyncpg's "can't subtract
    # offset-naive and offset-aware datetimes" (a live 500 discovered while
    # verifying Phase F). Stored values are still real UTC instants; only
    # the tzinfo marker is dropped to match what the column can hold.
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC).replace(tzinfo=None)}
    )


class TrustContribution(SQLModel, table=True):
    """
    Individual event contribution from a tenant to the global network.
    Schema: public (cross-tenant)
    """
    __tablename__ = "trust_contribution"
    __table_args__ = {"schema": "public", "extend_existing": True}

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Links to GlobalReputation
    phone_hash: str = Field(foreign_key="public.global_reputation.phone_hash", index=True, max_length=64)

    # Originating Tenant (for K-Anonymity and Reciprocity gates)
    tenant_id: str = Field(index=True, max_length=36)

    # Contribution Data
    outcome: ShipmentOutcome = Field(...)
    weight: Decimal = Field(
        default=Decimal("1.0000"),
        sa_column=Column(Numeric(10, 4), nullable=False)
    )
    is_disputed: bool = Field(default=False)

    # NOTE (Phase F fix, 2026-09-11): same naive-column fix as
    # GlobalReputation.updated_at above — this is also what
    # check_reciprocity_gate (app.modules.trust.services.gates) compares
    # against, so both sides must agree on naive UTC.
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
