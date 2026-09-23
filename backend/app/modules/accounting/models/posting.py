"""
app/modules/accounting/models/posting.py — GL Posting Ledger-Guard Record

WHY THIS EXISTS (P1 item 1 + 2, 15 Sep 2026)
--------------------------------------------
Before this, "has this business event already been posted to the GL?" was
answered by loose booleans scattered inside `Case.data`: gl_revenue_posted,
gl_receivable_posted, gl_payable_posted, commission_posted,
deployment_fee_posted, posting_failed, posting_error. Three problems, all
live-confirmed:

  1. THEY LIE. Case 01a0a1bc-9436-777a-8252-0f682c95d265 (14 Sep) carries BOTH
     `gl_revenue_posted: true` AND `posting_failed: true`, while the ledger
     holds ZERO journal entries for it. The flags contradict each other and
     both misdescribe reality — the posting genuinely never happened
     (ClosedPeriodError at the time).

  2. EACH MODULE TREATS THEM DIFFERENTLY. Only recruitment clears a stale
     `posting_failed` before retrying; hospitality/rental/travel leave it
     forever, so a case that later succeeded still looks broken.

  3. THE PROTECTION LIVES IN THE WRONG PLACE. Duplicate posting is currently
     prevented by `transition_case()`'s `SELECT ... FOR UPDATE` on the Case row
     (verified live: 5 concurrent confirms produced exactly 2 entries). That
     guard only covers the case-transition path. The ledger itself accepts
     duplicates — proven live by inserting two journal entries with the
     identical reference "DUP-TEST-001", both accepted (201, 201). Any path
     that does not hold the Case row lock (the manual journal-entry endpoint,
     an outbox/ARQ relay replay, a future publisher) can double-post.

GLPosting replaces all of that with ONE owned record per (source, kind), with
the uniqueness enforced by Postgres — not by remembering to check a flag:

    UNIQUE (source_type, source_id, entry_kind)

`entry_kind` is what makes a legitimate second posting for the same source
possible: a reversal is a DIFFERENT kind, so it is never blocked, while a
repeat of the SAME kind is refused by the database regardless of code path.

ENTRY KINDS IN USE (see app/modules/accounting/services/gl_posting.py)
----------------------------------------------------------------------
  hospitality_checkout_revenue      rental_return_revenue
  hospitality_cancellation_penalty  recruitment_commission
  travel_customer_receivable        recruitment_deployment_fee
  travel_supplier_payable           <any kind>_reversal
  travel_cancellation_refund
  travel_cancellation_penalty

MODEL STYLE: SQLModel (NOT raw SQLAlchemy Mapped[]).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import Column
from sqlmodel import Field

from app.core.db.base import TenantBase


class GLPostingStatus(str, enum.Enum):
    """Lifecycle of one GL posting attempt.

    RESERVED is written BEFORE the journal entry is created, inside the same
    transaction, so a crash between the two can never leave an orphan journal
    entry that nothing points at.
    """

    RESERVED = "RESERVED"   # claim taken, journal entry not confirmed yet
    POSTED = "POSTED"       # journal entry exists — journal_entry_id is set
    FAILED = "FAILED"       # attempt failed — error_type/error_message say why


class GLPosting(TenantBase, table=True):
    """One posting claim per (source_type, source_id, entry_kind).

    The UNIQUE constraint is the whole point: it is what makes double-posting
    structurally impossible instead of merely unlikely. Callers must go through
    app.modules.accounting.services.gl_posting.reserve_posting(), which uses
    INSERT ... ON CONFLICT DO NOTHING so a duplicate attempt is a quiet,
    idempotent no-op rather than an IntegrityError crash on a legitimate retry.
    """

    __tablename__ = "gl_postings"
    __table_args__ = (
        sa.UniqueConstraint(
            "source_type", "source_id", "entry_kind",
            name="uq_gl_postings_source_kind",
        ),
        sa.Index("ix_gl_postings_source", "source_type", "source_id"),
        sa.Index("ix_gl_postings_status", "status"),
        {"schema": "tenant"},
    )

    # ── Identity of the business event being posted ──────────────────────────
    source_type: str = Field(max_length=50, description="e.g. 'case'")
    source_id: uuid.UUID = Field(index=True, description="e.g. the Case id")
    entry_kind: str = Field(
        max_length=100,
        description="What kind of posting this is — see module docstring.",
    )

    # ── Outcome ──────────────────────────────────────────────────────────────
    status: GLPostingStatus = Field(
        sa_column=Column(
            # schema="tenant" is REQUIRED — without it SQLAlchemy emits an
            # unqualified CREATE TYPE that lands in public and is shared across
            # every tenant (the folio_item_category / employeestatus bug).
            sa.Enum(GLPostingStatus, name="gl_posting_status", schema="tenant"),
            nullable=False,
        )
    )
    journal_entry_id: uuid.UUID | None = Field(default=None, index=True)

    # ── Context, for humans reading the ledger ───────────────────────────────
    invoice_number: str | None = Field(default=None, max_length=100)
    amount: Decimal | None = Field(
        default=None, sa_column=Column(sa.Numeric(18, 4), nullable=True)
    )
    currency: str = Field(default="EGP", max_length=3)

    # ── Failure detail (surfaced to the user, not buried in a log) ───────────
    error_type: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, sa_column=Column(sa.Text, nullable=True))

    attempts: int = Field(default=1)
    last_attempt_at: datetime = Field(
        sa_column=Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    )
