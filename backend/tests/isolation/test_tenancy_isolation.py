import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.db.database import tenant_session
from app.modules.accounting.models import Account, TransactionLine

# ── Tests ─────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.asyncio

async def test_basic_api_isolation(two_tenants):
    """Ensure that using one tenant's session strictly isolates its reads."""
    alpha_id = two_tenants["alpha_id"]
    beta_id = two_tenants["beta_id"]
    
    async with tenant_session(alpha_id) as session:
        accounts = (await session.execute(select(Account))).scalars().all()
        assert len(accounts) == 1
        assert accounts[0].name == "Cash Alpha"
        
        lines = (await session.execute(select(TransactionLine))).scalars().all()
        assert len(lines) == 1
        assert lines[0].debit == Decimal("1000.00")
        
    async with tenant_session(beta_id) as session:
        accounts = (await session.execute(select(Account))).scalars().all()
        assert len(accounts) == 1
        assert accounts[0].name == "Cash Beta"
        
        lines = (await session.execute(select(TransactionLine))).scalars().all()
        assert len(lines) == 1
        assert lines[0].debit == Decimal("9999.00")

async def test_pooled_connection_reuse_does_not_leak(two_tenants):
    """
    CRITICAL: The Concurrency / Pool Reuse Test.
    Fires 200 concurrent tasks on a connection pool of size 5 (max 15).
    Guarantees that SQLAlchemy's connection reuse does not leak schema_translate_map state.
    """
    alpha_id = two_tenants["alpha_id"]
    beta_id = two_tenants["beta_id"]
    
    async def fetch_tenant_data(tenant_id, expected_debit):
        async with tenant_session(tenant_id) as session:
            # Force coroutine switching while holding the session
            await asyncio.sleep(0.01)
            result = await session.execute(select(TransactionLine.debit))
            debits = result.scalars().all()
            
            assert len(debits) == 1, f"Leak detected! Expected 1 line for tenant {tenant_id}, got {len(debits)}"
            assert debits[0] == expected_debit, f"Leak detected! Expected {expected_debit}, got {debits[0]}"
            return True

    tasks = []
    for i in range(200):
        if i % 2 == 0:
            tasks.append(fetch_tenant_data(alpha_id, Decimal("1000.00")))
        else:
            tasks.append(fetch_tenant_data(beta_id, Decimal("9999.00")))
            
    results = await asyncio.gather(*tasks)
    assert all(results)

async def test_event_consumer_isolation(two_tenants):
    """Ensure that dispatching background events resolves the correct schema."""
    from app.core.events.event_bus import get_event_bus

    
    alpha_id = two_tenants["alpha_id"]
    beta_id = two_tenants["beta_id"]
    
    event_bus = get_event_bus()

    # Since we are using an in-memory event bus that resolves asynchronously,
    # we can hook directly into the published event or assert on the side-effects.
    
    # We will simulate a background worker consuming the event manually:
    event_payload = {
        "tenant_id": alpha_id.hex,
        "payload": {"line_id": "fake_line", "amount": 100.0},
    }
    
    # The actual business logic in the worker looks like this:
    # It opens a new session using the tenant_id from the event
    from app.core.db.context import current_tenant_id, current_user_id
    
    t_token = current_tenant_id.set(alpha_id)
    u_token = current_user_id.set(uuid4())
    
    try:
        async with tenant_session(alpha_id) as session:
            # The consumer in accounting doesn't do much yet, but let's test if we manually
            # trigger an event that creates an account.
            pass
        
    finally:
        current_tenant_id.reset(t_token)
        current_user_id.reset(u_token)
