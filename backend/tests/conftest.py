"""
tests/conftest.py — Shared pytest fixtures

Provides:
  - In-memory async SQLite database (no PostgreSQL needed for unit tests)
  - InMemoryEventBus instance (no Redis needed)
  - Authenticated test client with a seeded tenant and user
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

# Override settings BEFORE importing the app
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["EVENT_BUS_BACKEND"] = "memory"
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-minimum!!"
os.environ["ENVIRONMENT"] = "development"

from app.core.database import AsyncSessionLocal, get_public_db, get_tenant_db  # noqa: E402
from app.core.event_bus import InMemoryEventBus, _bus_instance  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402


# ── Test Database Setup ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Create all tables in the in-memory test database."""
    # Import all models to register them with SQLModel.metadata
    import app.modules.system.models
    import app.modules.accounting.models
    import app.modules.contacts.models
    import app.plugins.inventory.models

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async database session per test (rolls back after each test)."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


# ── Test Tenant / User Fixtures ───────────────────────────────────────────────

TEST_TENANT_ID = uuid4()
TEST_USER_ID = uuid4()
TEST_ADMIN_ID = uuid4()


@pytest_asyncio.fixture
async def seed_tenant_and_users(db_session: AsyncSession):
    """Seed a test tenant, admin user, and staff user into the test DB."""
    from app.modules.system.models import Tenant, User, Subscription, TenantStatus, PlanTier

    tenant = Tenant(
        id=TEST_TENANT_ID,
        name="Test Merchant",
        slug="test-merchant",
        schema_name=f"tenant_{str(TEST_TENANT_ID).replace('-', '_')}",
        status=TenantStatus.ACTIVE,
        plan=PlanTier.FREE,
    )
    db_session.add(tenant)

    subscription = Subscription(tenant_id=TEST_TENANT_ID)
    db_session.add(subscription)

    admin_user = User(
        id=TEST_ADMIN_ID,
        tenant_id=TEST_TENANT_ID,
        email="admin@test.com",
        hashed_password=hash_password("AdminPass123"),
        full_name="Test Admin",
        roles=["admin"],
    )
    db_session.add(admin_user)

    staff_user = User(
        id=TEST_USER_ID,
        tenant_id=TEST_TENANT_ID,
        email="staff@test.com",
        hashed_password=hash_password("StaffPass123"),
        full_name="Test Staff",
        roles=["staff"],
    )
    db_session.add(staff_user)

    await db_session.commit()


# ── Test Accounting Fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_chart_of_accounts(db_session: AsyncSession, seed_tenant_and_users):
    """Create standard Chart of Accounts for accounting tests."""
    from app.modules.accounting.models import Account, AccountType

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
