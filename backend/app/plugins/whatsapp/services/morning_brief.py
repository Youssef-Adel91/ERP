"""
app/plugins/whatsapp/services/morning_brief.py — AI Roadmap Level 3: Cross-Tenant Fan-Out

Runs on a daily cron (see app.workers.tasks.main.run_whatsapp_morning_briefs)
and sends every ACTIVE tenant with at least one authorized WhatsApp number
(WhatsAppTenantConfig.authorized_numbers — the SAME allowlist
app.plugins.whatsapp.listeners.handle_whatsapp_message_ai_bot already
enforces and that was live-verified there; see that field's own docstring
for the data-leak reasoning) a short AI-narrated morning brief of their own
real numbers (app.modules.ai.morning_brief.build_morning_brief_text).

Best-effort by construction, same discipline as every other listener in
this plugin: one tenant's failure (AI provider down, a DB error building
the brief, Meta rejecting the send) is logged and skipped — it must never
stop the loop for every other tenant. Returns a summary dict so both the
cron log line and the manual admin-triggered endpoint
(POST /api/v1/whatsapp/morning-brief/run) can report exactly what happened.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.db.database import public_session, tenant_session
from app.modules.ai.morning_brief import build_morning_brief_text
from app.modules.system.models import Tenant, TenantStatus
from app.plugins.whatsapp.client import whatsapp_client
from app.plugins.whatsapp.models import WhatsAppTenantConfig

logger = logging.getLogger(__name__)


async def send_all_morning_briefs() -> dict:
    tenants_processed = 0
    messages_sent = 0
    failures: list[str] = []

    async with public_session() as public_db:
        result = await public_db.execute(
            select(WhatsAppTenantConfig).where(WhatsAppTenantConfig.is_active == True)  # noqa: E712
        )
        # authorized_numbers empty by default (see that field's docstring) —
        # a tenant with WhatsApp active but no authorized number yet gets no
        # brief, same "bot stays silent until the tenant opts in" rule as
        # the inbound AI Bot listener.
        configs = [c for c in result.scalars().all() if c.authorized_numbers]

        if not configs:
            logger.info("Morning briefs: no active WhatsApp configs with authorized_numbers — nothing to send.")
            return {"tenants_processed": 0, "messages_sent": 0, "failures": []}

        tenant_ids = {c.tenant_id for c in configs}
        tenant_rows = await public_db.execute(
            select(Tenant).where(Tenant.id.in_(tenant_ids), Tenant.status == TenantStatus.ACTIVE)
        )
        active_tenant_ids = {t.id for t in tenant_rows.scalars().all()}

    for config in configs:
        if config.tenant_id not in active_tenant_ids:
            continue

        tenants_processed += 1
        try:
            async with tenant_session(config.tenant_id) as tenant_db:
                text = await build_morning_brief_text(tenant_db)
        except Exception as exc:  # noqa: BLE001 — one tenant's failure must not stop the rest
            logger.error("Morning brief: failed to build brief for tenant %s: %s", config.tenant_id, exc)
            failures.append(f"{config.tenant_id}: build failed ({exc})")
            continue

        async with public_session() as public_db:
            for number in config.authorized_numbers:
                sent = await whatsapp_client.send_text_message(
                    session=public_db,
                    tenant_id=config.tenant_id,
                    phone_number=number,
                    text=text,
                )
                if sent is not None:
                    messages_sent += 1
                else:
                    # Best-effort, matches every other send in this plugin:
                    # whatsapp_client already logged the real reason
                    # (missing Meta credentials is the expected failure
                    # mode until a tenant has a real Access Token — same
                    # known limitation as §3.5/§3.7 in the project doc).
                    failures.append(f"{config.tenant_id}: send failed to {number}")

    logger.info(
        "Morning briefs: tenants_processed=%d messages_sent=%d failures=%d",
        tenants_processed, messages_sent, len(failures),
    )
    return {"tenants_processed": tenants_processed, "messages_sent": messages_sent, "failures": failures}
