from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Column
from sqlmodel import Field

from app.core.db.base import TenantBase


class ReconciliationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"

class ReconciliationRun(TenantBase, table=True):
    """
    Records the outcome of the Invariant Reconciliation Framework (the smoke alarm).
    
    If `status` is FAIL, `failed_checks` contains a JSON dump of exactly which
    invariants failed and the details (e.g., out of balance journal entry IDs,
    broken hash chain sequence numbers, or stale outbox event IDs).
    """
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        {"schema": "tenant", "extend_existing": True},
    )

    status: ReconciliationStatus = Field(
        sa_column=Column(
            sa.Enum(ReconciliationStatus, name="reconciliationstatus", schema="tenant"),
            nullable=False,
        ),
    )
    
    # JSON structure storing details of any failures
    failed_checks: dict | None = Field(
        default=None,
        sa_column=Column(sa.JSON, nullable=True),
    )
