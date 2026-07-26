"""
app/core/security/__init__.py — Backwards-Compatibility Re-exports

This package's __init__.py re-exports everything from security.security so
that imports like:
    from app.core.security import hash_password, decode_token
continue to work. The package shadows the old core/security.py module.

New code SHOULD import from the canonical location:
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
