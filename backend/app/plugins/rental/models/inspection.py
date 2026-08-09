"""
app/plugins/rental/models/inspection.py — Condition-at-Handover Tracking

Tenant-isolated model linked to case_id.
Captures snapshots at 'pickup' and 'return' to diff fuel, mileage, and damage.

MODEL STYLE: SQLModel (NOT raw SQLAlchemy Mapped[]).
  All fields must use SQLModel's Field() — never Mapped[].
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.core.db.base import TenantBase


class InspectionType(str, enum.Enum):
    PICKUP = "pickup"
    RETURN = "return"


class FuelLevel(str, enum.Enum):
    EMPTY          = "0/4"
    QUARTER        = "1/4"
    HALF           = "2/4"
    THREE_QUARTERS = "3/4"
    FULL           = "4/4"


class VehicleInspection(TenantBase, table=True):
    __tablename__ = "vehicle_inspections"
    __table_args__ = (
        sa.Index(
            "ix_vehicle_inspections_case_type",
            "case_id",
            "inspection_type",
            unique=True,
        ),
        {"schema": "tenant"},
    )

    case_id: uuid.UUID = Field(index=True)

    inspection_type: InspectionType = Field(
        sa_column=Column(
            sa.Enum(InspectionType, name="vehicle_inspection_type"),
            nullable=False,
        )
    )

    mileage: int = Field(
        sa_column=Column(sa.Numeric(10, 0), nullable=False)
    )
    fuel_level: FuelLevel = Field(
        sa_column=Column(
            sa.Enum(FuelLevel, name="vehicle_fuel_level"),
            nullable=False,
        )
    )

    # E.g., [{"location": "front_bumper", "type": "scratch", "severity": "minor", "photo_url": "..."}]
    damage_notes: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )

    inspected_by: str | None = Field(default=None, max_length=255)
    inspected_at: datetime = Field(
        sa_column=Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    )
    notes: str | None = Field(
        default=None,
        sa_column=Column(sa.Text, nullable=True),
    )
