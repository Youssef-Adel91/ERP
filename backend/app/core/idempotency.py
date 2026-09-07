"""
app/core/idempotency.py — HTTP Idempotency-Key Support for Create Endpoints

Sales/Purchasing/Inventory creation endpoints (POST /sales/invoices,
POST /purchasing/orders, POST /inventory/transfers, ...) have no built-in
protection against a client double-submit (network retry, double-click
before the button disables) — each POST unconditionally creates a new
row. This module adds an opt-in Idempotency-Key mechanism, following the
same Redis-backed, get/setex storage discipline already used by
app.core.security.security's refresh-token and password-reset-token
helpers (no NX locks — the in-memory `_FakeRedis` fallback in
app.core.db.database only implements get/setex/delete, so this stays
consistent with that fallback and with the rest of the codebase's Redis
usage).

Usage in a router:

    from app.core.db.database import get_redis
    from app.core.idempotency import IdempotencyKey, get_cached_resource_id, store_idempotent_result

    @router.post("")
    async def create_thing(
        data: ThingCreateRequest,
        current_user: CurrentUser,
        session: AsyncSession = Depends(get_tenant_db),
        redis: aioredis.Redis = Depends(get_redis),
        idempotency_key: str | None = IdempotencyKey,
    ) -> Thing:
        cached_id = await get_cached_resource_id(
            redis, tenant_id=current_user.tenant_id, endpoint="things.create", idempotency_key=idempotency_key,
        )
        if cached_id is not None:
            existing = await session.get(Thing, cached_id)
            if existing is not None:
                return existing
        ... create `thing`, session.commit() ...
        await store_idempotent_result(
            redis, tenant_id=current_user.tenant_id, endpoint="things.create",
            idempotency_key=idempotency_key, resource_id=thing.id,
        )
        return thing

On a cache hit the endpoint re-fetches the resource from the DB rather
than replaying a cached response body — cheaper to reason about (no JSON
serialization drift vs. the live response_model) and it's always exactly
what a fresh GET would return.
"""
from __future__ import annotations

import logging
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Header

logger = logging.getLogger(__name__)

# Same "reasonable TTL" window used for the analogous idempotency/dedupe
# stores elsewhere in this codebase (see app.modules.logistics.services
# .webhooks and app.modules.inventory.consumers.purchasing_events) —
# long enough to cover any realistic client retry, short enough not to
# accumulate stale keys forever.
_TTL_SECONDS = 24 * 60 * 60  # 24h

_KEY_PREFIX = "idempotency:"

# Route-parameter shorthand — use as `idempotency_key: str | None = IdempotencyKey`
# in route signatures. Optional by design: creation endpoints stay usable
# without the header, callers just don't get double-submit protection.
IdempotencyKey = Header(default=None, alias="Idempotency-Key")


def _redis_key(tenant_id: UUID | str, endpoint: str, idempotency_key: str) -> str:
    return f"{_KEY_PREFIX}{tenant_id}:{endpoint}:{idempotency_key}"


async def get_cached_resource_id(
    redis_client: aioredis.Redis,
    *,
    tenant_id: UUID | str,
    endpoint: str,
    idempotency_key: str | None,
) -> UUID | None:
    """
    Look up the resource id created by a prior request with this exact
    (tenant, endpoint, Idempotency-Key) combination.

    Returns None if idempotency_key is None (client didn't opt in — proceed
    normally) or if nothing is cached yet (first submission, or the 24h TTL
    already expired).
    """
    if not idempotency_key:
        return None
    raw: bytes | None = await redis_client.get(_redis_key(tenant_id, endpoint, idempotency_key))
    if raw is None:
        return None
    try:
        return UUID(raw.decode() if isinstance(raw, bytes) else raw)
    except (ValueError, AttributeError):
        logger.warning(
            "Malformed idempotency cache value for endpoint=%s tenant_id=%s", endpoint, tenant_id,
        )
        return None


async def store_idempotent_result(
    redis_client: aioredis.Redis,
    *,
    tenant_id: UUID | str,
    endpoint: str,
    idempotency_key: str | None,
    resource_id: UUID | str,
) -> None:
    """
    Remember which resource this (tenant, endpoint, Idempotency-Key) created,
    so a retried request with the same key returns it instead of creating a
    duplicate. No-op if idempotency_key is None.
    """
    if not idempotency_key:
        return
    await redis_client.setex(
        _redis_key(tenant_id, endpoint, idempotency_key),
        _TTL_SECONDS,
        str(resource_id),
    )
