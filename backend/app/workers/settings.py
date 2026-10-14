"""
app/workers/settings.py — ARQ Application Configuration

Configures the ARQ (Async Redis Queue) worker for background event processing.
"""
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.workers.tasks.main import (
    reconcile_provisioning,
    run_billing_cycle,
    run_invariants,
    run_whatsapp_morning_briefs,
    trigger_relay,
)

# ARCH-401: Queue Tiering Constants
QUEUE_CRITICAL = "arq:critical"   # Webhooks, synchronous-like background tasks
QUEUE_DEFAULT = "arq:default"     # Ledger posting, notifications
QUEUE_BULK = "arq:bulk"           # Data import/export, heavy reports
QUEUE_SCHEDULED = "arq:scheduled" # Cron jobs

async def startup(ctx: dict) -> None:
    """Startup hook for ARQ."""
    # arq injects the active Redis connection pool into ctx["redis"] automatically.
    # We can just keep it as is, or do any custom DB init here.
    from app.core.database import AsyncSessionLocal
    ctx["session_maker"] = AsyncSessionLocal
    
async def shutdown(ctx: dict) -> None:
    """Shutdown hook for ARQ."""
    pass

class WorkerSettings:
    """
    ARQ Worker Configuration.
    Run with: arq app.workers.settings.WorkerSettings
    """
    # Listen to the default queue unless overridden
    queue_name = QUEUE_DEFAULT
    
    functions = [
        run_invariants,
        reconcile_provisioning,
    ]
    
    cron_jobs = [
        # Aggressively drain the outbox every 1 second
        cron(trigger_relay, second=set(range(60))),
        # Subscription renewal + dunning sweep — was previously nothing:
        # process_failed_payment existed but had no scheduled trigger, so
        # a non-paying tenant never actually got suspended. Runs once a
        # day at 03:00 (low-traffic hour); the sweep is idempotent so a
        # missed/retried run is harmless.
        cron(run_billing_cycle, hour=3, minute=0),
        # AI roadmap Level 3 — daily WhatsApp morning brief. 05:00 UTC ≈
        # 07:00 Cairo (Africa/Cairo is UTC+2, no DST) — a reasonable
        # "before the workday starts" time. Per-tenant timezone-aware
        # scheduling (Tenant.timezone) is future work; every tenant gets
        # the same UTC slot for now, same MVP-first tradeoff already made
        # for accounting periods (see the project doc's §1 note on that).
        cron(run_whatsapp_morning_briefs, hour=5, minute=0),
    ]
    
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
