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
        # Default limits
        self.default_max_requests = max_requests
        self.default_window = window_seconds
        
        # Route-specific strict limits: (prefix, max_requests, window_seconds,
        # fail_closed). fail_closed=True means: if Redis is unreachable, DENY
        # the request instead of letting it through. This matters for
        # brute-force-sensitive routes (login, password reset, trust/erasure
        # operations) — silently disabling their rate limit the moment Redis
        # has a blip is exactly the window an attacker would want. Everything
        # else stays fail-open, since we'd rather keep the API serving
        # ordinary traffic than take a full outage over a Redis hiccup.
        self.strict_limits = [
            ("/api/v1/auth", 5, 60, True),
            ("/api/v1/trust", 10, 60, True),
            ("/api/v1/webhooks/carriers", 30, 60, False),
            ("/api/v1/invoices/public", 30, 60, False),
        ]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Determine strict limit by route prefix
        max_requests = self.default_max_requests
        window_seconds = self.default_window
        fail_closed = False

        for prefix, strict_max, strict_window, strict_fail_closed in self.strict_limits:
            if request.url.path.startswith(prefix):
                max_requests = strict_max
                window_seconds = strict_window
                fail_closed = strict_fail_closed
                break

        # Determine partitioning key
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id:
            key = f"rate_limit:tenant:{tenant_id}"
        else:
            # Fallback to IP address for unauthenticated requests
            client_ip = request.client.host if request.client else "unknown"
            key = f"rate_limit:ip:{client_ip}"
            
        current_window = int(time.time() // window_seconds)
        redis_key = f"{key}:{current_window}"

        try:
            # Increment the counter for this window
            # Use pipeline to ensure atomic execution and set TTL
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, window_seconds)
                result, _ = await pipe.execute()
                
            count = result
            
            if count > max_requests:
                return Response(
                    content='{"detail": "Too Many Requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(window_seconds)},
                )
        except RedisError as e:
            if fail_closed:
                logger.error(
                    f"Rate limiter DENY (fail-closed, Redis unreachable) on "
                    f"security-sensitive route {request.url.path}: {e}"
                )
                return Response(
                    content='{"detail": "Service temporarily unavailable. Please try again shortly."}',
                    status_code=503,
                    media_type="application/json",
                    headers={"Retry-After": "5"},
                )
            # If Redis is down, we gracefully bypass rate limiting on
            # non-security-critical routes to prevent the entire API from
            # going down over a Redis blip.
            logger.warning(f"Rate limiter bypass: Redis error: {e}")
        except Exception as e:
            logger.error(f"Rate limiter unexpected error: {e}")
        return await call_next(request)
