"""
app/core/security/middleware.py — Security Headers & Payload Restrictions
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Appends strict security headers to all outbound responses.
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests with payloads exceeding the specified maximum size (default 5MB).
    Can bypass specific routes using whitelist_prefixes.
    """
    def __init__(self, app, max_payload_size: int = 5 * 1024 * 1024, whitelist_prefixes: list[str] | None = None):
        super().__init__(app)
        self.max_payload_size = max_payload_size
        self.whitelist_prefixes = whitelist_prefixes or []

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check if route is whitelisted
        for prefix in self.whitelist_prefixes:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        # Check content-length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_payload_size:
                    return Response(
                        content='{"detail": "Payload Too Large"}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                # Malformed content-length header
                pass
                
        return await call_next(request)
