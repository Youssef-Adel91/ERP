"""
app/core/sequences/models.py — Gapless Document Sequence Model

Uses SELECT ... FOR UPDATE inside the caller's transaction to guarantee
zero-gap, serialized document numbering even under high concurrency.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.db.base import TenantBase


class DocumentSequence(TenantBase, table=True):
    """
    Per-(doc_type, branch_id, fiscal_year) counter for gapless document numbers.

    The UNIQUE constraint on (doc_type, branch_id, fiscal_year) ensures only one
    row exists per counter dimension, and SELECT ... FOR UPDATE serializes writers.
    """
    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint("doc_type", "branch_id", "fiscal_year", name="uq_doc_seq_type_branch_year"),
        {"schema": "tenant", "extend_existing": True},
    )

    doc_type: str = Field(max_length=50)
    branch_id: UUID | None = Field(default=None, nullable=True, index=True)
    fiscal_year: int = Field()                   # e.g. 2026
    prefix: str = Field(default="", max_length=20)   # e.g. "INV-", "JE-", "REC-"
    padding: int = Field(default=6)              # zero-pad width: 6 → 000001
    next_value: int = Field(default=1)
