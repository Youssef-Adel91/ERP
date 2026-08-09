"""
tests/conftest.py — Shared pytest fixtures

Provides:
  - In-memory async SQLite database (no PostgreSQL needed for unit tests)
  - InMemoryEventBus instance (no Redis needed)
  - Authenticated test client with a seeded tenant and user
"""
from __future__ import annotations

# Python 3.10 -> 3.11+ compatibility shim. The codebase targets Python
# 3.11+ (uses `from datetime import UTC` and `enum.StrEnum` directly,
# confirmed by [tool.mypy] python_version = "3.11" in pyproject.toml and
# the cpython-311 bytecode cache already present under tests/**/__pycache__
# from this suite's original run). This sandbox only has Python 3.10
# available, so both are polyfilled here, before any app.* import, purely
# so the suite is runnable in this environment. Harmless no-op on 3.11+.
import datetime as _datetime
import enum as _enum

if not hasattr(_datetime, "UTC"):
    _datetime.UTC = _datetime.timezone.utc
if not hasattr(_enum, "StrEnum"):
    class _StrEnum(str, _enum.Enum):
        pass
    _enum.StrEnum = _StrEnum

# Override settings BEFORE importing the app
import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["EVENT_BUS_BACKEND"] = "memory"
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-minimum!!"
os.environ["ENVIRONMENT"] = "development"

from app.core.database import get_public_db, get_tenant_db
from app.core.security import hash_password
from app.main import app

# ── Test Database Setup ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    future=True,
    execution_options={"schema_translate_map": {"tenant": None, "public": None}},
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables in the in-memory test database for each test."""
    from app.modules.approvals import models as _m1  # noqa: F401
    from app.modules.eta import models as _m2  # noqa: F401
    from app.modules.finance import models as _m6  # noqa: F401
    from app.modules.inventory import models as _m3  # noqa: F401
    from app.modules.logistics import models as _m4  # noqa: F401
    from app.modules.purchasing import models as _m5  # noqa: F401
    from app.modules.trust import models as _m7  # noqa: F401

    async with test_engine.begin() as conn:
        conn_translated = await conn.execution_options(schema_translate_map={"tenant": None, "public": None})
        await conn_translated.run_sync(SQLModel.metadata.drop_all)
        await conn_translated.run_sync(SQLModel.metadata.create_all)

    yield


@pytest_asyncio.fixture
async def db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async database session per test."""
    async with TestSessionLocal() as session:
        yield session


# ── Test Tenant / User Fixtures ───────────────────────────────────────────────

TEST_TENANT_ID = uuid4()
TEST_USER_ID = uuid4()
TEST_ADMIN_ID = uuid4()


@pytest_asyncio.fixture
async def seed_tenant_and_users(db_session: AsyncSession):
    """Seed a test tenant, admin user, and staff user into the test DB."""
    from app.modules.system.models import PlanTier, Tenant, TenantStatus, User, UserRole

    tenant = await db_session.get(Tenant, TEST_TENANT_ID)
    if tenant:
        return

    tenant = Tenant(
        id=TEST_TENANT_ID,
        name="Test Merchant",
        slug="test-merchant",
        schema_name=f"tenant_{str(TEST_TENANT_ID).replace('-', '_')}",
        status=TenantStatus.ACTIVE,
        plan=PlanTier.FREE,
    )
    db_session.add(tenant)



    admin_user = User(
        id=TEST_ADMIN_ID,
        tenant_id=TEST_TENANT_ID,
        email="admin@test.com",
        hashed_password=hash_password("AdminPass123"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
    )
    db_session.add(admin_user)

    staff_user = User(
        id=TEST_USER_ID,
        tenant_id=TEST_TENANT_ID,
        email="staff@test.com",
        hashed_password=hash_password("StaffPass123"),
        full_name="Test Staff",
        role=UserRole.STAFF,
    )
    db_session.add(staff_user)

    from datetime import UTC, datetime

    from app.modules.accounting.models import AccountingPeriod

    default_period = AccountingPeriod(
        name="Default Open Test Period",
        start_date=datetime(2020, 1, 1, tzinfo=UTC),
        end_date=datetime(2035, 12, 31, tzinfo=UTC),
        is_closed=False,
    )
    db_session.add(default_period)

    await db_session.commit()



# ── Test Accounting Fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_chart_of_accounts(db_session: AsyncSession, seed_tenant_and_users):
    """Create standard Chart of Accounts for accounting tests."""
    from sqlalchemy import select

    from app.modules.accounting.models import Account, AccountType
    existing_accounts = await db_session.execute(select(Account))
    if existing_accounts.scalars().first():
        accounts_list = (await db_session.execute(select(Account))).scalars().all()
        return {a.code: a for a in accounts_list}

    accounts = [
        Account(id=uuid4(), code="1110", name="Cash",                account_type=AccountType.ASSET),
        Account(id=uuid4(), code="1200", name="Accounts Receivable", account_type=AccountType.ASSET),
        Account(id=uuid4(), code="2100", name="Accounts Payable",    account_type=AccountType.LIABILITY),
        Account(id=uuid4(), code="4010", name="Revenue - Sales",     account_type=AccountType.REVENUE),
        Account(id=uuid4(), code="5010", name="Cost of Goods Sold",  account_type=AccountType.EXPENSE),
    ]

    for account in accounts:
        db_session.add(account)
    await db_session.commit()

    # Return dict for easy access in tests
    return {a.code: a for a in accounts}


# ── HTTP Test Client ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seed_tenant_and_users):
    """
    Async test client with dependency overrides.
    Both public_db and tenant_db are overridden with the test session.
    """
    async def override_public_db():
        yield db_session

    async def override_tenant_db():
        yield db_session

    app.dependency_overrides[get_public_db] = override_public_db
    app.dependency_overrides[get_tenant_db] = override_tenant_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {_get_admin_token()}",
            "X-Tenant-ID": str(TEST_TENANT_ID),
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def _get_admin_token() -> str:
    """Generate a test JWT for the admin user."""
    from app.core.security import create_access_token
    return create_access_token(
        user_id=TEST_ADMIN_ID,
        tenant_id=str(TEST_TENANT_ID),
        roles=["admin"],
    )
