"""
app/workers/tasks/utils.py — ARQ Tenant Worker Utilities
"""
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any
from uuid import UUID

from app.core.db.context import current_tenant_id
from app.core.db.database import tenant_session

logger = logging.getLogger(__name__)

# ARCH-402: Tenant Fairness Semaphore (Stub)
# In a true multi-tenant environment, if one tenant enqueues 1,000,000 jobs, 
# it can starve the worker pool for other tenants.
# To prevent this, we can use Redis to limit concurrency per tenant.
# Pseudocode implementation:
# async def acquire_tenant_lock(redis, tenant_id: UUID, max_concurrent: int = 10):
#     key = f"tenant-lock:{tenant_id}"
#     count = await redis.incr(key)
#     if count == 1:
#         await redis.expire(key, 600)  # TTL
#     if count > max_concurrent:
#         await redis.decr(key)
#         raise Exception("Tenant concurrency limit reached - retry later")
#     return True

def tenant_job(func: Callable) -> Callable:
    """
    Decorator for ARQ tasks that require tenant isolation.
    
    The decorated task MUST accept `tenant_id` as a keyword argument or as the second positional argument
    (after `ctx`).
    
    It injects an AsyncSession scoped to the tenant into the kwargs as `session`.
    """
    @wraps(func)
    async def wrapper(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        # Extract tenant_id from kwargs or args
        tenant_id = kwargs.get("tenant_id")
        if not tenant_id and len(args) > 0:
            tenant_id = args[0]
            
        if not tenant_id:
            raise ValueError(f"Task {func.__name__} requires a tenant_id")
            
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
            
        # ARCH-401 & ARCH-402: Optional fairness rate-limiting can go here
        
        token = current_tenant_id.set(str(tenant_id))
        try:
            async with tenant_session(tenant_id) as session:
                kwargs["session"] = session
                return await func(ctx, *args, **kwargs)
        finally:
            current_tenant_id.reset(token)
            
    return wrapper
