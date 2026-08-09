import asyncio
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, text

import uuid6
from app.modules.inventory.models import CostLayer, Item, StockLevel, CostingMethod
from app.modules.inventory.services.costing import consume_stock, CostingRequest
from app.modules.inventory.workers.recalculation import recalculate_cost_from_date
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import os
from sqlalchemy import text
from sqlmodel import SQLModel

pytestmark = pytest.mark.asyncio

ISOLATION_DB_URL = os.getenv("ISOLATION_DB_URL", "postgresql+asyncpg://postgres:postgres@localhost:5434/omni_erp")
SCHEMA = "tenant"

@pytest.fixture
async def tenant_engine():
    engine = create_async_engine(
        ISOLATION_DB_URL,
    ).execution_options(schema_translate_map={"tenant": SCHEMA, "public": "public"})
    
    async def clear_database(tenant_engine):
        async with tenant_engine.begin() as conn:
            # Drop all tables first to ensure clean schema (fixes missing columns if tables already existed)
            await conn.run_sync(SQLModel.metadata.drop_all)
            
            # We create all tables in the Postgres instance for the test
            await conn.run_sync(SQLModel.metadata.create_all)
            
            # We clear inventory tables for isolation (in case create_all skips)
            await conn.execute(text("TRUNCATE tenant.cost_layers, tenant.stock_levels, tenant.cost_consumptions, tenant.items CASCADE"))
            await conn.execute(text("DELETE FROM public.outbox_events"))

    await clear_database(engine)
    
    yield engine
    
    await clear_database(engine)
    await engine.dispose()

@pytest.fixture
def tenant_session_factory(tenant_engine):
    return async_sessionmaker(bind=tenant_engine, expire_on_commit=False)

@pytest.fixture
async def seeded_tenant(tenant_session_factory):
    tenant_id = uuid6.uuid7()
    return tenant_id

async def _run_consume(session_factory, item_id, warehouse_id, sem):
    """Worker to simulate a single stock consumption concurrently."""
    async with sem:
        async with session_factory() as session:
            try:
                request = CostingRequest(
                    item_id=item_id,
                    variant_id=None,
                    warehouse_id=warehouse_id,
                    quantity=Decimal("1"),
                    movement_type="OUT",
                    reference_id=f"LOAD-{uuid4()}"
                )
                await consume_stock(session, [request])
                await session.commit()
            except DBAPIError as e:
                if "deadlock detected" in str(e).lower():
                    raise e
                await session.rollback()
            except Exception:
                await session.rollback()


async def _run_recalculate(session_factory, tenant_id, item_id, warehouse_id, from_date, sem):
    """Worker to simulate a backdated recalculation request."""
    async with sem:
        try:
            # We pass a dummy context {}
            await recalculate_cost_from_date(
                {}, tenant_id, item_id, warehouse_id, from_date
            )
        except Exception:
            pass


@pytest.mark.timeout(300)
async def test_50k_costing_concurrency(tenant_session_factory, seeded_tenant):
    """
    The Phase 1a Gate: The 50k-Movement Concurrent Load Test.
    Simulates an asynchronous flood of 50,000 requests to prove zero deadlocks
    and perfect valuation math balance.
    """
    tenant_id = seeded_tenant
    item_id = uuid4()
    warehouse_id = uuid4()
    
    # 1. Seed Initial Stock Layer
    async with tenant_session_factory() as session:
        # Create an Item
        item = Item(
            id=item_id, 
            sku="TEST-50K-WAC", 
            name="Load Test Item",
            price=Decimal("10.0"),
            costing_method=CostingMethod.WAC
        )
        session.add(item)
        
        # Create initial huge layer
        layer = CostLayer(
            item_id=item_id,
            warehouse_id=warehouse_id,
            qty_received=Decimal("100000"),
            qty_remaining=Decimal("100000"),
            unit_cost_original=Decimal("5.0"),
            unit_cost_current=Decimal("5.0"),
            received_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        )
        session.add(layer)
        
        # Create stock level
        level = StockLevel(
            item_id=item_id,
            warehouse_id=warehouse_id,
            quantity=Decimal("100000")
        )
        session.add(level)
        await session.commit()

    # 2. Fire 50,000 concurrent requests!
    # To prevent overwhelming the connection pool/socket limits immediately, 
    # we use a bounded semaphore to throttle active connections to 50.
    sem = asyncio.BoundedSemaphore(50)
    
    tasks = []
    num_consumptions = 49990
    num_recalculations = 10
    
    # We will simulate 49,990 consumptions
    for _ in range(num_consumptions):
        tasks.append(_run_consume(tenant_session_factory, item_id, warehouse_id, sem))
        
    # And 10 random backdated recalculation triggers
    from_date = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=15)
    for _ in range(num_recalculations):
        tasks.append(_run_recalculate(tenant_session_factory, tenant_id, item_id, warehouse_id, from_date, sem))

    # Await all simultaneously
    await asyncio.gather(*tasks)
    
    # 3. Assertions
    async with tenant_session_factory() as session:
        # Check Stock Level
        level_stmt = select(StockLevel).where(StockLevel.item_id == item_id)
        final_level = (await session.execute(level_stmt)).scalar_one()
        
        # We started with 100,000 and consumed 49,990 * 1 = 49,990.
        # So we should have exactly 50,010 remaining.
        assert final_level.quantity == Decimal("50010")
        
        # Check Valuation Balance
        # Valuation should be 50,010 * 5.0 = 250,050.0
        val_query = text("""
            SELECT SUM(qty_remaining * unit_cost_current) as total_valuation
            FROM tenant.cost_layers
            WHERE item_id = :item_id
        """)
        val_result = await session.execute(val_query, {"item_id": item_id})
        valuation = Decimal(str(val_result.scalar() or 0))
        
        assert valuation == Decimal("250050.0000")
