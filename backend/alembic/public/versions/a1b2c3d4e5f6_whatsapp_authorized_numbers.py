"""whatsapp_authorized_numbers

Adds public.whatsapp_tenant_configs.authorized_numbers — a JSON list of
phone numbers (digits only, no '+', matching Meta's message.from format)
allowed to query the AI Bot over that tenant's WhatsApp Business number.

Needed because app.plugins.whatsapp.listeners.handle_whatsapp_message_ai_bot
(new: wires the already-live-verified AI Bot, app.modules.ai.router, to
inbound WhatsApp messages) must NOT reply to every inbound message — that
same Business number also receives real customer messages, and a customer
asking "كام المستحق؟" must never get back the tenant's own receivables.
Explicit allowlist, empty by default, so the bot stays silent over
WhatsApp until a tenant deliberately adds a number.

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-09-11 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'whatsapp_tenant_configs',
        sa.Column(
            'authorized_numbers',
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        schema='public',
    )


def downgrade() -> None:
    op.drop_column('whatsapp_tenant_configs', 'authorized_numbers', schema='public')
