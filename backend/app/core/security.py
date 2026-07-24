"""
app/core/security.py — Authentication & Cryptography

Responsibilities:
  - Password hashing (bcrypt)
  - JWT access token creation and decoding
  - Refresh token lifecycle in Redis (create / validate / revoke)
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis.asyncio as aioredis
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Password Hashing ──────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of a plain-text password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of plain password against bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Decoded JWT access token payload."""
    sub: str          # user_id (UUID string)
    tenant_id: str    # tenant_id (UUID string)
    roles: list[str]
    exp: int          # Unix timestamp


def create_access_token(
    user_id: UUID | str,
    tenant_id: str,
    roles: list[str],
) -> str:
    """
    Create a signed JWT access token (stateless, short-lived).

    Contains:
      sub       — user UUID
      tenant_id — tenant UUID
      roles     — list of role strings
      exp       — expiry Unix timestamp
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "tenant_id": tenant_id,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT access token.

    Raises:
        jose.JWTError — if token is invalid, expired, or tampered with.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return TokenPayload(
        sub=payload["sub"],
        tenant_id=payload["tenant_id"],
        roles=payload.get("roles", []),
        exp=payload["exp"],
    )


# ── Refresh Tokens (Redis-backed) ─────────────────────────────────────────────

_REFRESH_PREFIX = "refresh:"
_REFRESH_TTL_SECONDS = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400  # days → seconds


async def create_refresh_token(
    user_id: UUID | str,
    tenant_id: str,
    redis_client: aioredis.Redis,
) -> str:
    """
    Generate a cryptographically-secure refresh token and store it in Redis.

    Redis key: `refresh:{token}` → `{user_id}:{tenant_id}`
    TTL: REFRESH_TOKEN_EXPIRE_DAYS days

    This allows instant revocation: deleting the Redis key invalidates the token
    without needing to modify the DB or wait for JWT expiry.
    """
    token = secrets.token_urlsafe(64)  # 512 bits of entropy
    key = f"{_REFRESH_PREFIX}{token}"
    value = f"{user_id}:{tenant_id}"

    await redis_client.setex(key, _REFRESH_TTL_SECONDS, value)
    return token


async def validate_refresh_token(
    token: str,
    redis_client: aioredis.Redis,
) -> tuple[str, str] | None:
    """
    Look up a refresh token in Redis and return (user_id, tenant_id) if valid.

    Returns None if the token is expired or not found.
    Does NOT consume the token (unlike a one-time-use token).
    Call revoke_refresh_token() on logout.
    """
    key = f"{_REFRESH_PREFIX}{token}"
    raw: bytes | None = await redis_client.get(key)

    if raw is None:
        return None

    value = raw.decode("utf-8")
    parts = value.split(":", 1)
    if len(parts) != 2:
        logger.warning("Malformed refresh token value in Redis: %s", value)
        return None

    return parts[0], parts[1]  # user_id, tenant_id


async def revoke_refresh_token(
    token: str,
    redis_client: aioredis.Redis,
) -> bool:
    """
    Revoke a refresh token by deleting its Redis key.
    Safe to call on already-expired or non-existent tokens (returns False).
    """
    deleted = await redis_client.delete(f"{_REFRESH_PREFIX}{token}")
    return bool(deleted)


async def revoke_all_user_tokens(
    user_id: str,
    redis_client: aioredis.Redis,
) -> int:
    """
    Revoke ALL refresh tokens for a user (force-logout all sessions).
    Uses SCAN to find and delete all matching keys without blocking Redis.

    Returns the number of tokens revoked.
    """
    revoked = 0
    async for key in redis_client.scan_iter(match=f"{_REFRESH_PREFIX}*"):
        raw: bytes | None = await redis_client.get(key)
        if raw and raw.decode().startswith(f"{user_id}:"):
            await redis_client.delete(key)
            revoked += 1

    logger.info("Revoked %d refresh token(s) for user %s", revoked, user_id)
    return revoked
