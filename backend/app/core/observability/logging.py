"""
app/core/observability/logging.py — Structured Logging Configuration

Configures structlog to output JSON formatted logs with request-scoped
context variables (tenant_id, user_id, request_id, trace_id).
"""
import logging
import os
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

import structlog

# ── Context Variables ──────────────────────────────────────────────────────────
# These are bound per-request by the ObservabilityMiddleware
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


def add_context_vars(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Injects ContextVar values into the log event dictionary."""
    req_id = request_id_ctx.get()
    if req_id:
        event_dict["request_id"] = req_id

    trace_id = trace_id_ctx.get()
    if trace_id:
        event_dict["trace_id"] = trace_id

    tenant_id = tenant_id_ctx.get()
    if tenant_id:
        event_dict["tenant_id"] = tenant_id

    user_id = user_id_ctx.get()
    if user_id:
        event_dict["user_id"] = user_id

    return event_dict


def setup_logging(json_logs: bool = True, log_level: int = logging.INFO) -> None:
    """
    Configures structlog and the standard logging library.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            add_context_vars,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            add_context_vars,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Remove existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Also mirror all logs to a rotating file so tracebacks can be inspected
    # without needing to scroll back through a live terminal session.
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs")
        log_dir = os.path.abspath(log_dir)
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "backend.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError:
        # Never let log-file setup prevent the app from starting.
        pass

    root_logger.setLevel(log_level)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
