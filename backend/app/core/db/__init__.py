"""
app/core/db/__init__.py — Backwards-Compatibility Re-exports

Re-exports all public symbols from database.py so that
    from app.core.db import get_tenant_db
works as an alternative to
    from app.core.db.database import get_tenant_db
"""
from app.core.db.context import schema_for  # noqa: F401
from app.core.db.database import (  # noqa: F401
    AsyncSessionLocal,
    TenantMiddleware,
    drop_tenant_schema,
    engine,
    get_public_db,
    get_redis,
    get_tenant_db,
    provision_tenant_schema,
    public_session,
    redis_client,
    tenant_session,
)

create_tenant_schema = provision_tenant_schema
