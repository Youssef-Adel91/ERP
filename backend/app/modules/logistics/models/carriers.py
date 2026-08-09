"""
app.modules.logistics.models.carriers — Carrier Integration & Logistics Domain Models (Phase 7b)

Defines:
  1. ShipmentState: Canonical shipping status enum (FR-753).
  2. CarrierAccount: Tenant-specific carrier credentials and secrets stored by reference in Vault.
  3. Shipment: Core shipment tracking entity with FR-756 physical return marker.
  4. ShipmentEvent: Audit log of status transitions mapping raw carrier status to canonical state.
  5. CarrierWebhookEvent: Raw webhook ingestion log with dedupe_key for idempotency & replay protection.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, Numeric, String
from sqlmodel import Field

from app.core.db.base import TenantBase


class ShipmentState(StrEnum):
    """
    Canonical shipment states across all carriers (FR-753).
    Bosta, Mylerz, and future carriers map their raw statuses into this enum.
    """

    CREATED = "created"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNING = "returning"
    RETURNED = "returned"
    LOST = "lost"
    CANCELLED = "cancelled"


class CarrierAccount(TenantBase, table=True):
    """
    Per-tenant carrier account settings and credentials references (FR-750).
    Sensitive API keys/secrets are stored by reference in Vault (credentials_ref, webhook_secret_ref).
    """

    __table_args__ = (
        sa.UniqueConstraint("carrier_code", name="uq_carrier_account_code"),
        {"schema": "tenant"},
    )

    carrier_code: str = Field(index=True, nullable=False)
    credentials_ref: str = Field(nullable=False)
    webhook_secret_ref: str = Field(nullable=False)
    is_active: bool = Field(default=True, nullable=False)


class Shipment(TenantBase, table=True):
    """
    Shipment entity linked to a Sales Invoice (FR-750, FR-756).

    FR-756 Compliance Note:
        When `state` transitions to `ShipmentState.RETURNED`, inventory restock is NOT triggered automatically.
        Only setting `return_received_at` via an explicit warehouse physical check-in triggers restock.
    """

    __table_args__ = (
        sa.Index("ix_shipment_invoice_id", "invoice_id"),
        sa.Index("ix_shipment_awb", "awb_number"),
        sa.UniqueConstraint("carrier_code", "awb_number", name="uq_shipment_carrier_awb"),
        {"schema": "tenant"},
    )

    invoice_id: UUID = Field(nullable=False)
    carrier_code: str = Field(nullable=False)
    awb_number: str = Field(nullable=False)
    tracking_url: str | None = Field(default=None)
    state: ShipmentState = Field(
        default=ShipmentState.CREATED,
        sa_column=Column(String, nullable=False, default=ShipmentState.CREATED.value),
    )
    cod_amount: Decimal = Field(
        default=Decimal("0.0000"),
        sa_column=Column(Numeric(18, 4), nullable=False),
    )
    return_received_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
    )


class ShipmentEvent(TenantBase, table=True):
    """
    Audit trail of shipment status changes, mapping raw status to canonical state (FR-753, FR-760).
    """

    __table_args__ = (
        sa.Index("ix_shipment_event_shipment_id", "shipment_id"),
        {"schema": "tenant"},
    )

    shipment_id: UUID = Field(nullable=False)
    carrier_code: str = Field(nullable=False)
    carrier_status_raw: str = Field(nullable=False)
    canonical_state: ShipmentState = Field(
        sa_column=Column(String, nullable=False),
    )
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSON,
        sa_column_kwargs={"nullable": False},
    )
    event_time: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )


class CarrierWebhookEvent(TenantBase, table=True):
    """
    Inbound webhook storage for idempotency, replay protection, and audit (FR-752).
    A unique constraint on `dedupe_key` ensures duplicate webhooks are ignored immediately.
    """

    __table_args__ = (
        sa.UniqueConstraint("dedupe_key", name="uq_carrier_webhook_event_dedupe_key"),
        sa.Index("ix_carrier_webhook_dedupe", "dedupe_key"),
        {"schema": "tenant"},
    )

    carrier_code: str = Field(nullable=False)
    dedupe_key: str = Field(nullable=False)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSON,
        sa_column_kwargs={"nullable": False},
    )
    headers_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSON,
        sa_column_kwargs={"nullable": False},
    )
    signature_valid: bool = Field(default=True, nullable=False)
    received_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False},
    )
