"""
app/workers/settings.py — ARQ Application Configuration

Configures the ARQ (Async Redis Queue) worker for background event processing.
"""
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.workers.tasks.main import reconcile_provisioning, run_invariants, trigger_relay

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
    ]
    
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
