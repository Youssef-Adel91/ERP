"""
app/core/security.py — Backwards-Compatibility Shim

This file re-exports everything from the new canonical location:
    app.core.security.security

It exists so that legacy imports like:
    from app.core.security import decode_token, hash_password
continue to work without modification.

New code SHOULD import directly from:
    from app.core.security.security import ...
"""
from app.core.security.security import (  # noqa: F401
    RequireRole,
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    revoke_all_user_tokens,
    revoke_refresh_token,
    validate_refresh_token,
    verify_password,
)
