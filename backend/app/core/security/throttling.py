"""
app/core/security/throttling.py — Tenant-Aware Rate Limiting

Implements a Redis-based fixed-window rate limiter.
Keys are partitioned by tenant_id (if authenticated) or client IP.
"""
import logging
import time

from fastapi import Request, Response
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.db.database import redis_client

logger = logging.getLogger(__name__)

class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 300, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Determine partitioning key
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id:
            key = f"rate_limit:tenant:{tenant_id}"
        else:
            # Fallback to IP address for unauthenticated requests
            client_ip = request.client.host if request.client else "unknown"
            key = f"rate_limit:ip:{client_ip}"
            
        current_window = int(time.time() // self.window_seconds)
        redis_key = f"{key}:{current_window}"

        try:
            # Increment the counter for this window
            # Use pipeline to ensure atomic execution and set TTL
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, self.window_seconds)
                result, _ = await pipe.execute()
                
            count = result
            
            if count > self.max_requests:
                return Response(
                    content='{"detail": "Too Many Requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(self.window_seconds)},
                )
        except RedisError as e:
            # If Redis is down, we gracefully bypass rate limiting
            # to prevent the entire API from going down.
            logger.warning(f"Rate limiter bypass: Redis error: {e}")
        except Exception as e:
            logger.error(f"Rate limiter unexpected error: {e}")

        return await call_next(request)
