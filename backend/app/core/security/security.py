"""
app/core/security/security.py — Authentication & Cryptography

Responsibilities:
  - Password hashing (bcrypt)
  - JWT access token creation and decoding
  - Refresh token lifecycle in Redis (create / validate / revoke)
"""
from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import HTTPException, Request
from fastapi import status as http_status
from jose import jwt
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
    now = datetime.now(UTC)
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

    Returns None if the token is expired, not found, or has already been
    rotated out (tombstoned — see rotate_refresh_token() /
    detect_refresh_token_reuse() below; a rotated token is not "valid" for
    normal use even though its tombstone briefly still exists in Redis).
    Does NOT consume the token (unlike a one-time-use token).
    Call revoke_refresh_token() on logout, or rotate_refresh_token() on use.
    """
    key = f"{_REFRESH_PREFIX}{token}"
    raw: bytes | None = await redis_client.get(key)

    if raw is None:
        return None

    value = raw.decode("utf-8")
    if value.startswith(f"{_REUSE_MARKER}:"):
        return None  # tombstoned — already rotated out, not a live token

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

    Matches both live tokens (`{user_id}:{tenant_id}`) and reuse-detection
    tombstones (`REVOKED:{user_id}:{tenant_id}`, see rotate_refresh_token())
    so a full revoke leaves nothing — live or tombstoned — behind that could
    still be presented.

    Returns the number of tokens revoked.
    """
    revoked = 0
    async for key in redis_client.scan_iter(match=f"{_REFRESH_PREFIX}*"):
        raw: bytes | None = await redis_client.get(key)
        if not raw:
            continue
        value = raw.decode()
        if value.startswith(f"{user_id}:") or value.startswith(f"{_REUSE_MARKER}:{user_id}:"):
            await redis_client.delete(key)
            revoked += 1

    logger.info("Revoked %d refresh token(s) for user %s", revoked, user_id)
    return revoked


# ── Refresh Token Rotation & Reuse Detection ──────────────────────────────────
#
# Prior behaviour: the same refresh token could be exchanged for a new
# access token an unlimited number of times within its 7-day TTL (see
# validate_refresh_token() above, which is deliberately non-consuming).
# That means a refresh token leaked once (XSS, log capture, a compromised
# device) stays a valid, silent, long-lived credential for up to 7 days
# with zero signal to the real user or the server that anything is wrong.
#
# Fix: rotate-on-use. Every successful /auth/refresh call retires the
# presented token and issues a brand-new one (see rotate_refresh_token()).
# The retired token isn't deleted outright — it's replaced with a
# short-lived tombstone value (`REVOKED:{user_id}:{tenant_id}`) so that if
# it's presented again later (the classic sign of a stolen token racing
# the legitimate client, or an attacker replaying a captured token after
# the legitimate rotation already happened), detect_refresh_token_reuse()
# can recognise it as a reuse/compromise signal — at which point the
# caller (see app/modules/system/router.py::refresh_token) revokes *every*
# active refresh token for that user, not just the one being replayed.

_REUSE_MARKER = "REVOKED"
# How long a rotated-out token's tombstone survives, purely for reuse
# detection. Short by design: it only needs to outlive the realistic replay
# window (a stolen token being reused within seconds/minutes of rotation),
# not the full refresh-token TTL — keeping tombstones around for 7 days
# would just bloat Redis with dead keys for no added security benefit.
_REUSE_DETECTION_TTL_SECONDS = 5 * 60  # 5 minutes


async def rotate_refresh_token(
    old_token: str,
    user_id: UUID | str,
    tenant_id: str,
    redis_client: aioredis.Redis,
) -> str:
    """
    Atomically retire `old_token` (tombstoned for reuse detection, see
    module note above) and issue + store a brand-new refresh token.

    Callers MUST have already validated `old_token` via
    validate_refresh_token() before calling this — it does not re-validate.

    Returns the new refresh token string.
    """
    old_key = f"{_REFRESH_PREFIX}{old_token}"
    tombstone_value = f"{_REUSE_MARKER}:{user_id}:{tenant_id}"
    await redis_client.setex(old_key, _REUSE_DETECTION_TTL_SECONDS, tombstone_value)

    return await create_refresh_token(user_id, tenant_id, redis_client)


async def detect_refresh_token_reuse(
    token: str,
    redis_client: aioredis.Redis,
) -> tuple[str, str] | None:
    """
    Check whether `token` matches a tombstoned (already-rotated) refresh
    token — i.e. it was valid once, got exchanged via rotate_refresh_token(),
    and is now being presented again.

    Returns (user_id, tenant_id) if this is a reuse/compromise signal.
    Returns None if `token` doesn't exist in Redis at all, or exists but
    isn't a tombstone (e.g. it's a currently-live token — callers should
    check validate_refresh_token() for that case).
    """
    raw: bytes | None = await redis_client.get(f"{_REFRESH_PREFIX}{token}")
    if raw is None:
        return None

    value = raw.decode("utf-8")
    if not value.startswith(f"{_REUSE_MARKER}:"):
        return None

    parts = value.split(":", 2)
    if len(parts) != 3:
        logger.warning("Malformed reuse-tombstone value in Redis: %s", value)
        return None

    return parts[1], parts[2]  # user_id, tenant_id


# ── Password Reset Tokens (Redis-backed, one-time-use) ────────────────────────
#
# Same storage discipline as refresh tokens above: a high-entropy random
# token is the Redis key itself (never the DB), so possession of the token
# IS the credential and revocation is an instant Redis delete — no JWT
# denylist or DB column needed. Deliberately NOT reusing create_access_token
# — a password-reset token must not double as a bearer credential for the
# API, must be single-use, and needs a much shorter TTL than an access
# token, so a dedicated Redis-backed token (mirroring the refresh-token
# pattern) is the right tool, not a JWT with a different `exp`.

_PASSWORD_RESET_PREFIX = "pwreset:"
_PASSWORD_RESET_TTL_SECONDS = settings.RESET_TOKEN_EXPIRE_MINUTES * 60


async def create_password_reset_token(
    user_id: UUID | str,
    redis_client: aioredis.Redis,
) -> str:
    """
    Generate a cryptographically-secure, single-use password-reset token
    and store it in Redis.

    Redis key: `pwreset:{token}` → `{user_id}`
    TTL: RESET_TOKEN_EXPIRE_MINUTES minutes (short-lived by design).
    """
    token = secrets.token_urlsafe(48)
    key = f"{_PASSWORD_RESET_PREFIX}{token}"
    await redis_client.setex(key, _PASSWORD_RESET_TTL_SECONDS, str(user_id))
    return token


async def validate_password_reset_token(
    token: str,
    redis_client: aioredis.Redis,
) -> str | None:
    """
    Look up a password-reset token in Redis and return the associated
    user_id if it exists and hasn't expired. Returns None otherwise.

    Does NOT consume the token — callers MUST call
    invalidate_password_reset_token() once the reset actually succeeds, so
    a token can't be replayed if e.g. the DB update fails after this check.
    """
    raw: bytes | None = await redis_client.get(f"{_PASSWORD_RESET_PREFIX}{token}")
    if raw is None:
        return None
    return raw.decode("utf-8")


async def invalidate_password_reset_token(
    token: str,
    redis_client: aioredis.Redis,
) -> bool:
    """
    Invalidate a password-reset token by deleting its Redis key, so it
    cannot be used a second time. Safe to call on an already-invalid or
    non-existent token (returns False).
    """
    deleted = await redis_client.delete(f"{_PASSWORD_RESET_PREFIX}{token}")
    return bool(deleted)


# ── Client Portal OTP (Redis-backed, one-time-use) ────────────────────────────
#
# Same storage discipline as password-reset tokens above, adapted for a
# short numeric code instead of a high-entropy URL token: a 6-digit OTP has
# far less entropy than secrets.token_urlsafe(), so — unlike the reset
# token, which IS the Redis key — the code here is hashed with the same
# bcrypt context used for account passwords (_pwd_context, via
# hash_password/verify_password) and stored as the Redis VALUE, keyed by
# `{tenant_id}:{contact_id}`, with a bounded number of verification
# attempts before the code is invalidated outright. This closes the brute
# -force gap a raw 6-digit code would otherwise have within its TTL window.

_PORTAL_OTP_PREFIX = "portal_otp:"
_PORTAL_OTP_TTL_SECONDS = 5 * 60  # 5 minutes — short-lived by design
_PORTAL_OTP_MAX_ATTEMPTS = 5


def _portal_otp_key(tenant_id: UUID | str, contact_id: UUID | str) -> str:
    return f"{_PORTAL_OTP_PREFIX}{tenant_id}:{contact_id}"


async def create_portal_otp(
    tenant_id: UUID | str,
    contact_id: UUID | str,
    redis_client: aioredis.Redis,
) -> str:
    """
    Generate a random 6-digit numeric OTP for a Client Portal login, store
    its bcrypt hash in Redis (never the plain code), and return the plain
    code so the caller can deliver it over a real channel (WhatsApp/email —
    see app.core.notifications.dispatch.notify_contact).

    Redis key: `portal_otp:{tenant_id}:{contact_id}` →
        json {"hash": <bcrypt hash>, "attempts": 0}
    TTL: PORTAL_OTP_TTL_SECONDS (5 minutes).

    Overwrites any previously-issued, still-valid OTP for this contact —
    only the most recently requested code is ever accepted, and resending
    resets the attempt counter.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"  # cryptographically secure, zero-padded
    key = _portal_otp_key(tenant_id, contact_id)
    value = json.dumps({"hash": hash_password(code), "attempts": 0})
    await redis_client.setex(key, _PORTAL_OTP_TTL_SECONDS, value)
    return code


async def verify_portal_otp(
    tenant_id: UUID | str,
    contact_id: UUID | str,
    code: str,
    redis_client: aioredis.Redis,
) -> bool:
    """
    Verify a submitted OTP against the hash stored in Redis for this
    tenant/contact. Single-use: the Redis key is deleted immediately on a
    correct match, so the same code cannot be replayed. Also deleted once
    PORTAL_OTP_MAX_ATTEMPTS wrong guesses have been made, so a leaked/
    guessed-at code can't be brute-forced within its TTL window.

    Returns True iff the code matched; False for no-such-code (expired/
    never issued/already consumed), too-many-attempts, or a wrong code.
    """
    key = _portal_otp_key(tenant_id, contact_id)
    raw: bytes | None = await redis_client.get(key)
    if raw is None:
        return False

    try:
        data = json.loads(raw.decode("utf-8"))
        stored_hash = data["hash"]
        attempts = int(data.get("attempts", 0))
    except (ValueError, KeyError, TypeError):
        logger.warning("Malformed portal OTP value in Redis for key=%s", key)
        await redis_client.delete(key)
        return False

    if attempts >= _PORTAL_OTP_MAX_ATTEMPTS:
        await redis_client.delete(key)
        return False

    if not verify_password(code, stored_hash):
        attempts += 1
        if attempts >= _PORTAL_OTP_MAX_ATTEMPTS:
            await redis_client.delete(key)
        else:
            await redis_client.setex(
                key, _PORTAL_OTP_TTL_SECONDS, json.dumps({"hash": stored_hash, "attempts": attempts}),
            )
        return False

    await redis_client.delete(key)  # single-use — consume on success
    return True


# ── Role-based access control helper ─────────────────────────────────────────

def require_role(*allowed_roles: "UserRole | str"):
    """
    Reusable FastAPI dependency factory for role-based access control (RBAC).

    Thin, more-idiomatic wrapper around RequireRole() below — same
    request.state.current_user_roles check (populated by the tenancy
    middleware from the JWT's `roles` claim, see app/core/db/database.py),
    just accepting UserRole enum members (or plain strings) as *args instead
    of a mixed positional/list signature, so call sites read naturally with
    the app.modules.system.models.UserRole enum:

        from app.core.security.security import require_role
        from app.modules.system.models import UserRole

        @router.delete(
            "/{user_id}",
            dependencies=[Depends(require_role(UserRole.OWNER, UserRole.ADMIN))],
        )
        async def delete_user(...): ...

        # Or applied to a single route without a dedicated dependencies=[]:
        @router.post("/settings")
        async def update_settings(
            current_user: CurrentUser,
            _: None = Depends(require_role(UserRole.OWNER)),
        ): ...

    Raises HTTPException(403) if none of `allowed_roles` match the caller's
    role(s). Raises nothing (passes) if `allowed_roles` is empty — an empty
    allow-list is almost certainly a bug at the call site, so callers should
    always pass at least one role; this function does not guess a safe
    default for you.

    This is the module-agnostic, framework-level building block. Enforcing
    it endpoint-by-endpoint across every module (billing, inventory, POS,
    etc.) is intentionally OUT OF SCOPE here — each module owner should
    import and apply this to their own sensitive endpoints (user
    management, settings, financial close, void/refund, etc.) as a
    follow-up pass.
    """
    role_values = {r.value if hasattr(r, "value") else str(r) for r in allowed_roles}
    return RequireRole(list(role_values))


def RequireRole(roles_or_first, *extra_roles: str):
    """
    FastAPI dependency factory for role-based access control.

    Returns an async callable (not a Depends object). Usage:
        dependencies=[Depends(RequireRole(["OWNER"]))]
        dependencies=[Depends(RequireRole("OWNER", "ADMIN"))]

    Accepts either:
      RequireRole("OWNER")              — single role
      RequireRole("OWNER", "ADMIN")     — multiple roles via *args
      RequireRole(["OWNER", "ADMIN"])   — list (used by some routers)
    """
    # Normalise to a flat list of role strings
    if isinstance(roles_or_first, list):
        roles = list(roles_or_first)
    else:
        roles = [roles_or_first, *extra_roles]

    async def _check(request: Request):
        user_roles: list = getattr(request.state, "current_user_roles", [])
        if not any(r in user_roles for r in roles):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {roles}.",
            )

    return _check  # Return callable, NOT Depends — callers wrap with Depends()
