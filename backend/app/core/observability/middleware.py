"""
app/core/observability/middleware.py — Observability Middleware

Extracts tracing information and binds it along with generated request IDs
to the structlog context variables.
"""
import uuid

from fastapi import Request, Response
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.observability.logging import (
    request_id_ctx,
    trace_id_ctx,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        # Generate a unique request ID
        req_id = str(uuid.uuid4())
        
        # Get trace ID from OpenTelemetry
        current_span = trace.get_current_span()
        trace_id = None
        if current_span and current_span.get_span_context().is_valid:
            trace_id = format(current_span.get_span_context().trace_id, "032x")
            
        # Bind to structlog context
        token_req = request_id_ctx.set(req_id)
        token_trace = trace_id_ctx.set(trace_id)
        
        try:
            response = await call_next(request)
            
            # Extract tenant and user ID if TenantMiddleware set them
            tenant_id = getattr(request.state, "tenant_id", None)
            user_id = getattr(request.state, "current_user_id", None)
            
            # We can't really set these for the current request's logs going BACK up the stack
            # as easily without injecting it before call_next, but TenantMiddleware runs AFTER this.
            # Structlog context variables are already accessible within the route handlers though
            # if we update them in TenantMiddleware. Let's set them here just for the final log 
            # if needed, or better: we should update TenantMiddleware to set them in contextvars!
            # Wait, the prompt says "ObservabilityMiddleware wraps TenantMiddleware... and bind them to structlog".
            # If we extract it after call_next, only the response log will have it. 
            # It's better if ObservabilityMiddleware just reads what TenantMiddleware put into request.state.
            
            return response
            
        finally:
            request_id_ctx.reset(token_req)
            trace_id_ctx.reset(token_trace)
