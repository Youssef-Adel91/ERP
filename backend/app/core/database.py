"""
app/core/database.py — Backwards-Compatibility Shim

This file re-exports everything from the new canonical location:
    app.core.db.database

It exists so that legacy imports like:
    from app.core.database import get_tenant_db
continue to work without modification in alembic/env.py and tests.

New code SHOULD import directly from:
    from app.core.db.database import ...
"""
from app.core.db.database import (  # noqa: F401
    AsyncSessionLocal,
    TenantMiddleware,
    _schema_name,
    drop_tenant_schema,
    engine,
    get_public_db,
    get_redis,
    get_tenant_db,
    provision_tenant_schema,
    redis_client,
)

# Alias for code that uses the old name (pre-existing in system/service.py)
create_tenant_schema = provision_tenant_schema
