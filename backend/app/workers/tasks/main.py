"""
app/workers/tasks/main.py — Main ARQ Tasks
"""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.relay import relay_tick
from app.core.observability.invariants import run_all_invariants
from app.workers.tasks.utils import tenant_job


@tenant_job
async def run_invariants(ctx: dict[str, Any], tenant_id: UUID, session: AsyncSession) -> None:
    """Run tenant invariants/consistency checks."""
    await run_all_invariants(session, tenant_id)

@tenant_job
async def reconcile_provisioning(ctx: dict[str, Any], tenant_id: UUID, session: AsyncSession) -> None:
    """Stub for tenant provisioning logic."""
    pass

async def trigger_relay(ctx: dict[str, Any]) -> None:
    """
    Cron job to trigger the Transactional Outbox relay.
    Note: We need a redis client here to pass to relay_tick.
    ARQ injects 'redis' into the ctx during startup if we define on_startup.
    """
    redis = ctx.get("redis")
    if redis:
        await relay_tick(redis)
