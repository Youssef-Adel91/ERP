"""
app/workers/tasks/main.py — Main ARQ Tasks
"""
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.relay import relay_tick
from app.core.observability.invariants import run_all_invariants
from app.workers.tasks.utils import tenant_job

logger = logging.getLogger(__name__)


@tenant_job
async def run_invariants(ctx: dict[str, Any], tenant_id: UUID, session: AsyncSession) -> None:
    """Run tenant invariants/consistency checks."""
    await run_all_invariants(session, tenant_id)

async def reconcile_provisioning(ctx: dict[str, Any], tenant_id: str) -> None:
    """
    Retry/backfill path for tenant schema provisioning.

    Registration provisions a tenant's schema via a detached subprocess
    (app.core.db.database.provision_tenant_schema) so a crash or restart
    mid-provisioning can leave a tenant with no schema, or a partially
    migrated one. Enqueue this task to safely retry: both CREATE SCHEMA IF
    NOT EXISTS and `alembic upgrade head` are idempotent, so re-running
    this against an already fully-provisioned tenant is a safe no-op.

    NOT wrapped in @tenant_job — that decorator opens a tenant_session
    (SET search_path to the tenant schema) which assumes the schema
    already exists; this task's entire job is to make sure it does.
    """
    from sqlalchemy import text

    from app.core.db.database import engine
    from app.core.db.context import schema_for
    from app.core.tenancy.migrations import TenantMigrationOrchestrator

    if isinstance(tenant_id, UUID):
        tenant_id = str(tenant_id)

    schema = schema_for(tenant_id)
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    orchestrator = TenantMigrationOrchestrator()
    try:
        await orchestrator._migrate_tenant(schema)
        logger.info("Reconcile provisioning: tenant=%s schema=%s migrated to head.", tenant_id, schema)
    except Exception:
        logger.exception("Reconcile provisioning failed for tenant=%s schema=%s", tenant_id, schema)
        raise

async def trigger_relay(ctx: dict[str, Any]) -> None:
    """
    Cron job to trigger the Transactional Outbox relay.
    Note: We need a redis client here to pass to relay_tick.
    ARQ injects 'redis' into the ctx during startup if we define on_startup.
    """
    redis = ctx.get("redis")
    if redis:
        await relay_tick(redis)


async def run_billing_cycle(ctx: dict[str, Any]) -> None:
    """
    Cron job: generates due subscription renewal invoices and re-sweeps
    overdue ones through the real dunning engine (see
    app.modules.billing.services.recurring.run_billing_cycle). Billing is
    public-schema (cross-tenant, not per-tenant data), so this uses
    public_session() directly rather than the tenant_job decorator.

    Before this existed, process_failed_payment (dunning) was fully
    implemented but had no scheduled trigger — a subscription that simply
    never got paid would sit in whatever state it was last left in,
    forever, since nothing ever re-checked overdue invoices on a clock.
    """
    from app.core.db.database import public_session
    from app.modules.billing.services.recurring import run_billing_cycle as _run_billing_cycle

    async with public_session() as session:
        try:
            result = await _run_billing_cycle(session)
            logger.info("Billing cycle cron: %s", result)
        except Exception:
            logger.exception("Billing cycle cron failed")


async def run_whatsapp_morning_briefs(ctx: dict[str, Any]) -> None:
    """
    Cron job: AI roadmap Level 3 — daily AI-narrated WhatsApp morning brief
    to every tenant with at least one authorized number (see
    app.plugins.whatsapp.models.WhatsAppTenantConfig.authorized_numbers).
    Cross-tenant fan-out (public-schema first, then one tenant_session per
    eligible tenant inside the service function itself), same reasoning as
    run_billing_cycle above — this is NOT wrapped in @tenant_job, which
    assumes a single already-known tenant_id.
    """
    from app.plugins.whatsapp.services.morning_brief import send_all_morning_briefs

    try:
        result = await send_all_morning_briefs()
        logger.info("Morning brief cron: %s", result)
    except Exception:
        logger.exception("Morning brief cron failed")
