"""
app/modules/ai/models.py — AI Roadmap Level 4: Agentic Document Drafting

Adopts app.core.models.mixins.DocumentLifecycleMixin (the SAME universal
state machine + content-hash tamper protection every other approvable
document in this codebase uses — see app.modules.purchasing.models.core
.PurchaseOrder for the existing precedent) so an AI-drafted customer-facing
message goes through the EXACT same real approval engine
(app.modules.approvals) as a purchase order, rather than a bespoke
"AI approval" mechanism. This is the whole point of Level 4 per the AI
roadmap: the AI drafts, a human approves, and only after a real recorded
APPROVE decision does anything go out to a real customer — see
app.plugins.whatsapp.listeners.handle_ai_draft_approved for what happens
next.

Deliberately scoped to ONE document type for the first live-verified slice:
an overdue-payment WhatsApp reminder, drafted from the exact same real
overdue-invoice data app.modules.reporting.service.get_overdue_invoices
already uses (see app.modules.ai.document_drafting.draft_overdue_payment_reminder)
— never invented numbers, same grounding discipline as Level 1/2/3.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field

from app.core.db.base import TenantBase
from app.core.models.mixins import DocumentLifecycleMixin


class AIDraftPurpose(StrEnum):
    OVERDUE_PAYMENT_REMINDER = "overdue_payment_reminder"


class AIDraftChannel(StrEnum):
    WHATSAPP = "whatsapp"


class AIDraftedMessage(DocumentLifecycleMixin, TenantBase, table=True):
    """
    document_type string used with the Approval Engine
    (app.modules.approvals) is the literal "ai_drafted_message" — see
    app.modules.approvals.api._resolve_document_model and
    app.modules.ai.router's submit-for-approval endpoint.
    """

    __tablename__ = "ai_drafted_messages"
    __table_args__ = ({"schema": "tenant"},)

    purpose: AIDraftPurpose = Field(
        sa_column=Column(
            sa.Enum(AIDraftPurpose, name="aidraftpurpose", schema="tenant", create_type=False),
            nullable=False,
        )
    )
    channel: AIDraftChannel = Field(
        default=AIDraftChannel.WHATSAPP,
        sa_column=Column(
            sa.Enum(AIDraftChannel, name="aidraftchannel", schema="tenant", create_type=False),
            default=AIDraftChannel.WHATSAPP,
            nullable=False,
        ),
    )
    contact_id: UUID = Field(index=True)
    draft_text: str = Field(sa_column=Column(Text, nullable=False))
    # The real grounded data (invoice numbers/amounts) the draft was built
    # from — kept for audit, so an approver (or a later investigation) can
    # see exactly what facts justified the message text, same "drill
    # through to source transactions" guardrail as the reporting layer.
    grounding_data: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(sa.JSON, nullable=False)
    )
    sent_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    send_error: str | None = Field(default=None, max_length=500)
