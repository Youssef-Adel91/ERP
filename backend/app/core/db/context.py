"""
app/core/db/context.py — Request-Scoped Context Variables

ContextVars replace thread-locals in async code. Each asyncio Task inherits
a copy of the parent's ContextVar state at creation time, which means
asyncio.create_task() (used for background event handlers) gets the correct
tenant context from the request that spawned it.

This module is the single source of truth for:
  - current_tenant_id  → which tenant is being served
  - current_user_id    → who is making the request
  - current_session    → the active AsyncSession (avoids passing it everywhere)
  - schema_for()       → deterministic tenant → schema_name converter

Architecture note:
  These ContextVars are SET by the session context managers in database.py
  (tenant_session / public_session) and READ anywhere in the call stack
  without needing explicit parameter threading.
"""
from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

# ── Per-request Context Variables ─────────────────────────────────────────────

current_tenant_id: ContextVar[UUID | None] = ContextVar(
    "current_tenant_id", default=None,
)

current_user_id: ContextVar[str | None] = ContextVar(
    "current_user_id", default=None,
)

current_session: ContextVar[AsyncSession | None] = ContextVar(
    "current_session", default=None,
)


# ── Schema Naming ─────────────────────────────────────────────────────────────


def schema_for(tenant_id: UUID | str) -> str:
    """
    Convert a tenant UUID to its canonical PostgreSQL schema name.

    Preserves the existing naming convention (dashes → underscores) so that
    schemas created by the old code are still reachable.

    Examples:
        schema_for("550e8400-e29b-41d4-a716-446655440000")
        → "tenant_550e8400_e29b_41d4_a716_446655440000"

        schema_for(UUID("550e8400-e29b-41d4-a716-446655440000"))
        → "tenant_550e8400_e29b_41d4_a716_446655440000"
    """
    return f"tenant_{str(tenant_id).replace('-', '_')}"
