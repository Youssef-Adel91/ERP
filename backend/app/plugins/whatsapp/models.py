"""
app/plugins/whatsapp/models.py — Per-Tenant WhatsApp Business API Configuration

Schema placement: PUBLIC, not tenant. This was originally schema="tenant"
(see git history), but that's architecturally incompatible with the
inbound webhook flow: Meta calls ONE global webhook URL for the whole
platform and the payload only carries `phone_number_id` — the tenant is
not known yet. Resolving phone_number_id -> tenant_id requires a
cross-tenant lookup, which is only possible on a public-schema table
(the same reasoning that put Trust Network's global_reputation and
Billing's Plan/Subscription in `public` earlier in this project).
phone_number_id therefore also carries a UNIQUE constraint here — it's
the reverse-lookup key inbound webhooks use to find the owning tenant,
so two tenants can never share one.

Follows the precedent set by app.modules.eta.models.core.EtaTenantConfig
for secrets: the long-lived bearer credential (access_token) is never
stored in plaintext — only a Vault reference string, resolved at
send-time by app.plugins.whatsapp.services.vault.resolve_access_token
(same simulated-Vault pattern as EtaGateway._resolve_client_secret /
trust.services.hashing.get_vault_pepper — no live Vault client exists in
this project, all three are intentionally-labeled stand-ins).
webhook_verify_token is a lower-sensitivity, self-chosen value (the
tenant picks it and gives it to Meta, not the other way around), so it's
stored directly.

Now wired end-to-end: app.plugins.whatsapp.client.WhatsAppClient
(outbound) and app.plugins.whatsapp.api.webhooks (inbound) both resolve
per-tenant config from this table instead of reading global
app.core.config.settings values.
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Column
from sqlmodel import Field

from app.core.db.base import PublicBase


class WhatsAppTenantConfig(PublicBase, table=True):
    """
    Note: PublicBase already provides created_at/updated_at (auto-updated
    on write), so no separate timestamp column is needed here.
    """

    __tablename__ = "whatsapp_tenant_configs"
    __table_args__ = ({"schema": "public"},)

    tenant_id: UUID = Field(index=True, unique=True)

    # Unique: this is the reverse-lookup key inbound Meta webhooks use to
    # resolve which tenant owns an incoming message. Must never collide.
    phone_number_id: str = Field(max_length=100, unique=True, index=True)
    access_token_ref: str | None = Field(default=None, max_length=255)
    webhook_verify_token: str | None = Field(default=None, max_length=255)

    is_active: bool = Field(default=False)

    # Phone numbers (as sent by Meta in message.from — digits only, no
    # '+') allowed to talk to the AI Bot over this tenant's WhatsApp
    # number. Deliberately an explicit allowlist rather than "reply to
    # anyone who messages this number": that same number also receives
    # real customer messages, and a customer asking "كام المستحق؟" must
    # never get back the tenant's own receivables — see
    # app.plugins.whatsapp.listeners.handle_whatsapp_message_ai_bot,
    # which checks this list BEFORE calling the AI Bot at all. Empty by
    # default: the bot is silent over WhatsApp for a tenant until they
    # explicitly add at least one number via PUT /api/v1/whatsapp/config.
    authorized_numbers: list[str] = Field(
        default_factory=list,
        sa_column=Column(sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
    )
