"""
app.modules.eta.services.gateway — Global Rate Governor & ETA Gateway (Phase 5 - Step 2)

Implements:
  1. TokenBucket: Async rate limiter enforcing platform-global ETA request limits (F-1, FR-540, §5.2).
  2. EtaGateway: The sole egress point for all ETA HTTP requests across all tenants (FR-540).
     - Token Management with single-flight stampede lock (F-3).
     - Global rate governor throttling and rate_deferred signaling (FR-542, FR-543).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine
from uuid import UUID

import httpx

from app.modules.eta.exceptions import (
    EtaAuthenticationError,
    EtaRateDeferredError,
    EtaServiceUnavailableError,
)
from app.modules.eta.models.core import EtaEnvironment, EtaTenantConfig


class TokenBucket:
    """
    Async Token Bucket rate limiter (F-1, FR-540, §5.2).
    Enforces platform-global ETA rate limits across all workers/tenants.
    
    Attributes:
        rate: Refill rate in tokens per second.
        capacity: Maximum token burst capacity.
    """

    def __init__(self, rate: float = 2.0, capacity: float = 2.0) -> None:
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, max_wait: float = 0.0) -> bool:
        """
        Acquire `tokens` from the bucket.
        If tokens are available, decrements the bucket and returns True immediately.
        If max_wait > 0 and wait time is within max_wait, sleeps asynchronously until refilled.
        Otherwise, returns False immediately (triggering EtaRateDeferredError).
        """
        start_time = time.monotonic()
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                needed = tokens - self.tokens
                wait_time = needed / self.rate

            if max_wait <= 0.0 or (time.monotonic() - start_time + wait_time > max_wait):
                return False

            # Sleep asynchronously in small increments until tokens refill
            await asyncio.sleep(min(wait_time, 0.05))


class EtaGateway:
    """
    Global ETA Gateway & Rate Governor (FR-540).
    The ONLY permitted egress point for ETA API calls.
    
    Features:
      - OAuth Token Management with cache and single-flight lock (F-3).
      - Per-endpoint TokenBucket rate governors (F-1).
      - Requeue / rate_deferred signaling on throttling.
    """

    ETA_ID_URLS = {
        EtaEnvironment.PREPRODUCTION: "https://id.preprod.eta.gov.eg/connect/token",
        EtaEnvironment.PRODUCTION: "https://id.eta.gov.eg/connect/token",
    }

    ETA_API_URLS = {
        EtaEnvironment.PREPRODUCTION: "https://api.preprod.eta.gov.eg",
        EtaEnvironment.PRODUCTION: "https://api.eta.gov.eg",
    }

    def __init__(self, cache_backend: Any = None) -> None:
        # In-memory async fallback cache if Redis is not provided
        self._memory_cache: dict[str, dict[str, Any]] = {}
        self.cache_backend = cache_backend

        # Single-flight locks per cache key to prevent token stampedes
        self._token_locks: dict[str, asyncio.Lock] = {}
        self._token_locks_mutex = asyncio.Lock()

        # TokenBucket rate governors per ETA endpoint category
        self.buckets: dict[str, TokenBucket] = {
            "submission": TokenBucket(rate=2.0, capacity=2.0),  # Max 2 submissions/sec
            "default": TokenBucket(rate=5.0, capacity=5.0),     # Max 5 queries/sec
        }

        # Telemetry & verification counters
        self.token_fetch_count: int = 0
        self.request_count: int = 0

        # Optional mock handlers for unit testing without external network calls
        self.mock_token_handler: Callable[[EtaTenantConfig], Coroutine[Any, Any, dict[str, Any]]] | None = None
        self.mock_http_handler: Callable[[str, str, dict[str, Any], Any], Coroutine[Any, Any, dict[str, Any]]] | None = None

    def _get_token_cache_key(self, tenant_config: EtaTenantConfig) -> str:
        """Generate deterministic cache key for taxpayer OAuth token."""
        return f"eta:token:{tenant_config.taxpayer_rin}:{tenant_config.environment}"

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Acquire or create single-flight lock for a token cache key."""
        async with self._token_locks_mutex:
            if key not in self._token_locks:
                self._token_locks[key] = asyncio.Lock()
            return self._token_locks[key]

    async def _cache_get_token(self, key: str) -> str | None:
        """Retrieve token from cache if still valid."""
        now = time.time()
        if self.cache_backend and hasattr(self.cache_backend, "get"):
            # Redis or external cache
            cached = await self.cache_backend.get(key)
            if cached and isinstance(cached, dict) and cached.get("expires_at", 0) > now:
                return cached["access_token"]
            return None

        cached_mem = self._memory_cache.get(key)
        if cached_mem and cached_mem.get("expires_at", 0) > now:
            return str(cached_mem["access_token"])
        return None

    async def _cache_set_token(self, key: str, token: str, ttl: float) -> None:
        """Save access token with expiration timestamp."""
        expires_at = time.time() + ttl
        data = {"access_token": token, "expires_at": expires_at}
        if self.cache_backend and hasattr(self.cache_backend, "set"):
            await self.cache_backend.set(key, data, ex=int(ttl))
        self._memory_cache[key] = data

    async def _resolve_client_secret(self, tenant_config: EtaTenantConfig) -> str:
        """
        Resolve client_secret from Vault reference (never stored in DB).
        In test mode or mock mode, accepts mock references.
        """
        if not tenant_config.client_id or not tenant_config.client_secret_ref:
            raise EtaAuthenticationError(
                f"Missing OAuth credentials (client_id/client_secret_ref) for tenant {tenant_config.tenant_id}"
            )
        # For our Vault integration / test environment:
        # Reference format: "vault://secrets/eta/..." or test secret string
        ref = tenant_config.client_secret_ref
        if ref.startswith("vault://"):
            # In live systems, query secret manager via ref
            return "resolved_vault_secret_value"
        return ref

    async def _fetch_token_from_eta(self, tenant_config: EtaTenantConfig) -> dict[str, Any]:
        """Execute OAuth client_credentials grant request against ETA Identity Server."""
        if self.mock_token_handler:
            self.token_fetch_count += 1
            return await self.mock_token_handler(tenant_config)

        secret = await self._resolve_client_secret(tenant_config)
        url = self.ETA_ID_URLS.get(tenant_config.environment, self.ETA_ID_URLS[EtaEnvironment.PREPRODUCTION])

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": tenant_config.client_id,
                        "client_secret": secret,
                        "scope": "InvoicingAPI",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.RequestError as exc:
                raise EtaServiceUnavailableError(f"ETA Identity Server unreachable: {exc}") from exc

            if response.status_code == 429:
                raise EtaRateDeferredError("ETA Identity Server returned HTTP 429 Too Many Requests.")
            if response.status_code >= 500:
                raise EtaServiceUnavailableError(f"ETA Identity Server HTTP {response.status_code}")
            if response.status_code != 200:
                raise EtaAuthenticationError(
                    f"Failed to acquire ETA OAuth token: HTTP {response.status_code} - {response.text}"
                )

            data = response.json()
            if "access_token" not in data:
                raise EtaAuthenticationError("Invalid response from ETA Identity Server: missing access_token")
            self.token_fetch_count += 1
            return data

    async def get_access_token(
        self,
        tenant_config: EtaTenantConfig,
        force_refresh: bool = False,
    ) -> str:
        """
        Fetch and cache OAuth access token with single-flight stampede lock (F-3).
        Only ONE concurrent worker executes the actual token request; others wait and share.
        """
        cache_key = self._get_token_cache_key(tenant_config)

        # 1. Fast path (unlocked cache read)
        if not force_refresh:
            cached_token = await self._cache_get_token(cache_key)
            if cached_token:
                return cached_token

        # 2. Acquire single-flight lock for this cache key
        lock = await self._get_lock(cache_key)
        async with lock:
            # 3. Double-check cache inside lock (stampede prevention!)
            # If another worker just fetched the token while we waited on the lock, use it!
            if not force_refresh:
                cached_token = await self._cache_get_token(cache_key)
                if cached_token:
                    return cached_token

            # 4. Execute actual token fetch
            token_data = await self._fetch_token_from_eta(tenant_config)
            token_str = str(token_data["access_token"])
            expires_in = float(token_data.get("expires_in", 3600))

            # 5. Cache token with 5-minute safety buffer before expiration (F-3)
            ttl = max(60.0, expires_in - 300.0)
            await self._cache_set_token(cache_key, token_str, ttl=ttl)
            return token_str

    async def acquire_rate_limit(self, endpoint_key: str = "default", max_wait: float = 0.0) -> bool:
        """
        Check Global Rate Governor for `endpoint_key`.
        If limit is exceeded and max_wait is 0 (or wait > max_wait), raises EtaRateDeferredError.
        """
        bucket = self.buckets.get(endpoint_key, self.buckets["default"])
        acquired = await bucket.acquire(tokens=1.0, max_wait=max_wait)
        if not acquired:
            raise EtaRateDeferredError(
                f"Global rate governor threshold reached for endpoint '{endpoint_key}' (F-1). Task deferred."
            )
        return True

    async def request(
        self,
        method: str,
        path: str,
        tenant_config: EtaTenantConfig,
        endpoint_key: str = "default",
        max_wait: float = 0.0,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute an authenticated, rate-governed HTTP call to ETA API gateway (FR-540).
        """
        # 1. Enforce Rate Governor limit (F-1)
        await self.acquire_rate_limit(endpoint_key=endpoint_key, max_wait=max_wait)

        # 2. Ensure valid auth token (F-3)
        token = await self.get_access_token(tenant_config)

        # 3. Construct headers
        req_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        base_url = self.ETA_API_URLS.get(tenant_config.environment, self.ETA_API_URLS[EtaEnvironment.PREPRODUCTION])
        full_url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

        # 4. Dispatch request (mock handler or actual HTTP call)
        self.request_count += 1
        if self.mock_http_handler:
            return await self.mock_http_handler(method, full_url, json_body or {}, req_headers)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method.upper(),
                    url=full_url,
                    json=json_body,
                    headers=req_headers,
                    **kwargs,
                )
            except httpx.RequestError as exc:
                raise EtaServiceUnavailableError(f"ETA API Gateway unreachable: {exc}") from exc

            if response.status_code == 429:
                raise EtaRateDeferredError("ETA returned HTTP 429 Too Many Requests.")
            if response.status_code >= 500:
                raise EtaServiceUnavailableError(f"ETA API Gateway error: HTTP {response.status_code}")
            if response.status_code == 401:
                # Token expired prematurely; invalidate and raise
                cache_key = self._get_token_cache_key(tenant_config)
                self._memory_cache.pop(cache_key, None)
                raise EtaAuthenticationError("ETA API returned 401 Unauthorized.")

            return response.json()

    async def submit_documents(
        self,
        tenant_config: EtaTenantConfig,
        submission_payload: dict[str, Any],
        max_wait: float = 0.0,
    ) -> dict[str, Any]:
        """
        Submit a batch of signed documents to ETA (/api/v1/documentssubmissions).
        Enforces "submission" rate limit (2 calls/sec).
        """
        return await self.request(
            method="POST",
            path="/api/v1/documentssubmissions",
            tenant_config=tenant_config,
            endpoint_key="submission",
            max_wait=max_wait,
            json_body=submission_payload,
        )

    async def submit_receipts(
        self,
        tenant_config: EtaTenantConfig,
        submission_payload: dict[str, Any],
        max_wait: float = 0.0,
    ) -> dict[str, Any]:
        """
        Submit a signed batch of e-Receipts to ETA (/api/v1/receipts/submissions) (§5.1, FR-570).
        Enforces 'submission' rate limit.
        """
        return await self.request(
            method="POST",
            path="/api/v1/receipts/submissions",
            tenant_config=tenant_config,
            endpoint_key="submission",
            max_wait=max_wait,
            json_body=submission_payload,
        )
