import os
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import SQLModel

from app.modules.accounting.models import (
    Account,
    AccountType,
    JournalEntry,
    JournalEntryStatus,
    TransactionLine,
)
from app.modules.system.models import PlanTier, Tenant, TenantStatus

# We need fixed UUIDs so we can attach the databases in on_connect
ALPHA_ID = uuid4()
BETA_ID = uuid4()
ALPHA_SCHEMA = f"tenant_{str(ALPHA_ID).replace('-', '_')}"
BETA_SCHEMA = f"tenant_{str(BETA_ID).replace('-', '_')}"

# ── Isolation Database Engine ─────────────────────────────────────────────────

# We use real files for SQLite to guarantee they survive across connection checkouts
ISOLATION_DB_URL = "sqlite+aiosqlite:///isolation_main.db"

# We must use an AsyncAdaptedQueuePool to simulate connection pooling and reuse.
# pool_size=5 means we will reuse these 5 connections for our 200 concurrent requests!
isolation_engine = create_async_engine(
    ISOLATION_DB_URL,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=5,
    max_overflow=10,
    connect_args={"check_same_thread": False},
)

# Use SQLAlchemy's sync event to attach our simulated schemas to EVERY connection
# as soon as it's created by the pool.
@event.listens_for(isolation_engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    # We simulate schemas by attaching real file databases.
    # In aiosqlite, dbapi_connection may be a proxy, but it supports execute()
    dbapi_connection.execute(f"ATTACH DATABASE 'tenant_alpha.db' AS {ALPHA_SCHEMA}")
    dbapi_connection.execute(f"ATTACH DATABASE 'tenant_beta.db' AS {BETA_SCHEMA}")
    dbapi_connection.execute("ATTACH DATABASE 'public.db' AS public")

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_isolation_database():
    """Create tables in the respective schemas."""
    # We must explicitly create tables in the attached databases.
    # Since SQLModel.metadata.create_all uses schema names, and SQLite attached databases
    # act like schemas, this will natively create the tables in `tenant_alpha` and `tenant_beta`!
    
    # Clean up old files
    for f in ["tenant_alpha.db", "tenant_beta.db", "public.db", "isolation_main.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    async with isolation_engine.begin() as conn:
        # Create public tables
        conn_public = await conn.execution_options(schema_translate_map={"tenant": None, "public": "public"})
        await conn_public.run_sync(SQLModel.metadata.drop_all)
        await conn_public.run_sync(SQLModel.metadata.create_all)
        
        # We manually generate and execute DDL because SQLite dialect ignores schema in DDL
        def create_tenant_tables(connection, schema_name):
            for table in SQLModel.metadata.tables.values():
                if table.schema == "tenant":
                    # Create Table
                    create_stmt = str(CreateTable(table).compile(isolation_engine.sync_engine))
                    # SQLite dialect usually omits schema or puts 'main.'
                    create_stmt = create_stmt.replace(f"CREATE TABLE tenant.{table.name}", f"CREATE TABLE {schema_name}.{table.name}")
                    create_stmt = create_stmt.replace(f"CREATE TABLE main.{table.name}", f"CREATE TABLE {schema_name}.{table.name}")
                    create_stmt = create_stmt.replace(f"CREATE TABLE {table.name}", f"CREATE TABLE {schema_name}.{table.name}")
                    # Remove schema from REFERENCES for SQLite
                    create_stmt = create_stmt.replace("REFERENCES tenant.", "REFERENCES ")
                    create_stmt = create_stmt.replace("REFERENCES main.", "REFERENCES ")
                    connection.execute(text(create_stmt))
                    
                    # Create Indexes
                    for index in table.indexes:
                        idx_stmt = str(CreateIndex(index).compile(isolation_engine.sync_engine))
                        idx_stmt = idx_stmt.replace(f"ON tenant.{table.name}", f"ON {table.name}")
                        idx_stmt = idx_stmt.replace(f"ON main.{table.name}", f"ON {table.name}")
                        idx_stmt = idx_stmt.replace(f"ON {schema_name}.{table.name}", f"ON {table.name}")
                        idx_stmt = idx_stmt.replace("CREATE INDEX tenant.", f"CREATE INDEX {schema_name}.")
                        idx_stmt = idx_stmt.replace("CREATE UNIQUE INDEX tenant.", f"CREATE UNIQUE INDEX {schema_name}.")
                        idx_stmt = idx_stmt.replace("CREATE INDEX main.", f"CREATE INDEX {schema_name}.")
                        idx_stmt = idx_stmt.replace("CREATE UNIQUE INDEX main.", f"CREATE UNIQUE INDEX {schema_name}.")
                        idx_stmt = idx_stmt.replace(f"CREATE INDEX {index.name}", f"CREATE INDEX {schema_name}.{index.name}")
                        idx_stmt = idx_stmt.replace(f"CREATE UNIQUE INDEX {index.name}", f"CREATE UNIQUE INDEX {schema_name}.{index.name}")
                        connection.execute(text(idx_stmt))

        await conn.run_sync(lambda c: create_tenant_tables(c, ALPHA_SCHEMA))
        await conn.run_sync(lambda c: create_tenant_tables(c, BETA_SCHEMA))
        
    yield


@pytest_asyncio.fixture(scope="session")
async def two_tenants(setup_isolation_database):
    """Seed the database with two isolated tenants and their respective data."""
    # Tenant Alpha
    alpha_id = ALPHA_ID
    # Tenant Beta
    beta_id = BETA_ID
    
    SessionLocal = async_sessionmaker(bind=isolation_engine, expire_on_commit=False)
    
    async with SessionLocal() as session:
        # 1. Seed Public Tenants.
        # We can't set execution_options on session easily, so we yield a specific connection
        conn = await isolation_engine.connect()
        conn_pub = await conn.execution_options(schema_translate_map={"tenant": None, "public": "public"})
        session_pub = AsyncSession(bind=conn_pub, expire_on_commit=False)
        session_pub.add(Tenant(id=alpha_id, name="Tenant Alpha", slug="alpha", schema_name=ALPHA_SCHEMA, status=TenantStatus.ACTIVE, plan=PlanTier.FREE))
        session_pub.add(Tenant(id=beta_id, name="Tenant Beta", slug="beta", schema_name=BETA_SCHEMA, status=TenantStatus.ACTIVE, plan=PlanTier.FREE))
        await session_pub.commit()
        await session_pub.close()
        await conn.close()

    # A better way is to use our app's tenant_session
    # We need to temporarily override the app's engine for these tests
    import app.core.db.database as db_module
    from app.core.db.database import tenant_session
    original_engine = getattr(db_module, "engine", None)
    
    # Mock the module engine variables to use isolation_engine
    db_module.engine = isolation_engine
    db_module.AsyncSessionLocal = async_sessionmaker(isolation_engine, expire_on_commit=False)
    
    try:
        # Setup Alpha Data
        async with tenant_session(alpha_id) as session_alpha:
            acc_alpha = Account(id=uuid4(), code="1000", name="Cash Alpha", account_type=AccountType.ASSET)
            session_alpha.add(acc_alpha)
            res = await session_alpha.execute(text(f"SELECT name FROM {ALPHA_SCHEMA}.sqlite_master WHERE type='table'"))
            print(f"TABLES IN {ALPHA_SCHEMA} FOR SESSION ALPHA:", res.fetchall())
            await session_alpha.flush()
            
            je_alpha = JournalEntry(id=uuid4(), reference="JE-ALPHA", description="Alpha Entry", status=JournalEntryStatus.POSTED, created_by=uuid4())
            session_alpha.add(je_alpha)
            await session_alpha.flush()
            
            session_alpha.add(TransactionLine(id=uuid4(), journal_entry_id=je_alpha.id, account_code=acc_alpha.code, debit=Decimal("1000.00")))
            await session_alpha.commit()
            
        # Setup Beta Data
        async with tenant_session(beta_id) as session_beta:
            acc_beta = Account(id=uuid4(), code="1000", name="Cash Beta", account_type=AccountType.ASSET)
            session_beta.add(acc_beta)
            await session_beta.flush()
            
            je_beta = JournalEntry(id=uuid4(), reference="JE-BETA", description="Beta Entry", status=JournalEntryStatus.POSTED, created_by=uuid4())
            session_beta.add(je_beta)
            await session_beta.flush()
            
            session_beta.add(TransactionLine(id=uuid4(), journal_entry_id=je_beta.id, account_code=acc_beta.code, debit=Decimal("9999.00")))
            await session_beta.commit()

        yield {"alpha_id": alpha_id, "beta_id": beta_id}
        
    finally:
        db_module.engine = original_engine
        # restore session maker to normal engine
        if original_engine:
            db_module.AsyncSessionLocal = async_sessionmaker(original_engine, expire_on_commit=False)
