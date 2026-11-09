"""Portal tokens must never be accepted as staff access tokens."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security.security import create_access_token, decode_token


def _portal_token() -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "type": "portal_access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def test_portal_token_rejected_as_access_token():
    with pytest.raises(JWTError):
        decode_token(_portal_token())


def test_access_token_roundtrip():
    uid, tid = uuid4(), str(uuid4())
    payload = decode_token(create_access_token(uid, tid, ["OWNER"]))
    assert payload.sub == str(uid) and payload.tenant_id == tid and payload.roles == ["OWNER"]


# ── Role gating on sensitive routers ─────────────────────────────────────────
import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from app.core.security.security import RequireRoleForWrites


def _req(method: str, roles: list[str]):
    return SimpleNamespace(method=method, state=SimpleNamespace(current_user_roles=roles))


def test_writes_gate_blocks_wrong_role_but_allows_reads():
    check = RequireRoleForWrites("OWNER", "ACCOUNTING")
    asyncio.run(check(_req("GET", ["STAFF"])))  # reads open
    with pytest.raises(HTTPException) as e:
        asyncio.run(check(_req("POST", ["STAFF"])))
    assert e.value.status_code == 403


def test_writes_gate_allows_permitted_role():
    asyncio.run(RequireRoleForWrites("OWNER", "ACCOUNTING")(_req("DELETE", ["ACCOUNTING"])))
