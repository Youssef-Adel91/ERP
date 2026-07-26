import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import uuid6
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.observability.invariants import run_all_invariants
from app.core.observability.models import ReconciliationStatus
from app.modules.accounting.models import JournalEntry, JournalEntryStatus, TransactionLine

ISOLATION_DB_URL = os.getenv("ISOLATION_DB_URL", "postgresql+asyncpg://postgres:postgres@db:5432/omni_erp")
SCHEMA = "tenant"

@pytest.fixture
async def tenant_engine():
    engine = create_async_engine(
        ISOLATION_DB_URL,
    ).execution_options(schema_translate_map={"tenant": SCHEMA, "public": "public"})
    
    async def clear_database(tenant_engine):
        async with tenant_engine.begin() as conn:
            await conn.execute(text("TRUNCATE tenant.journal_entries, tenant.transaction_lines CASCADE"))
            await conn.execute(text("DELETE FROM public.outbox_events"))

    await clear_database(engine)
    
    yield engine
    
    await clear_database(engine)
        
    await engine.dispose()

@pytest.fixture
async def public_engine():
    engine = create_async_engine(
        ISOLATION_DB_URL,
    ).execution_options(schema_translate_map={"public": "public"})
    yield engine
    await engine.dispose()

@pytest.fixture
def tenant_session_factory(tenant_engine):
    return async_sessionmaker(bind=tenant_engine, expire_on_commit=False)

@pytest.fixture
async def seeded_tenant(tenant_session_factory, public_engine):
    """Seeds a tenant with healthy ledger and healthy outbox."""
    tenant_id = uuid6.uuid7()
    
    # 1. Seed Outbox (healthy)
    async with public_engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO public.outbox_events (id, tenant_id, aggregate_type, aggregate_id, event_type, event_version, payload, occurred_at, attempts)
                VALUES (:id, :tenant_id, 'test', :tenant_id, 'test.event', 1, '{"test": 1}', :occurred_at, 0)
            """),
            {
                "id": uuid6.uuid7(),
                "tenant_id": tenant_id,
                "occurred_at": datetime.now(UTC),  # Not stale yet
            },
        )
        
    # 2. Seed Journal Entries
    async with tenant_session_factory() as session:
        # Seed an entry
        import hashlib

        from app.modules.accounting.services.hash import _canonical_payload
        
        # We manually build and insert an entry since posting requires a complex environment
        entry_id = uuid6.uuid7()
        line1_id = uuid6.uuid7()
        line2_id = uuid6.uuid7()
        
        lines = [
            TransactionLine(account_code="1000", debit=Decimal("100.0"), credit=Decimal("0.0"), currency="EGP"),
            TransactionLine(account_code="4000", debit=Decimal("0.0"), credit=Decimal("100.0"), currency="EGP"),
        ]
        
        je = JournalEntry(
            id=entry_id,
            sequence_no=1,
            reference="TEST-000001",
            description="Test Entry",
            status=JournalEntryStatus.POSTED,
            posted_at=datetime.utcnow(),
            prev_hash="0" * 64,
        )
        
        canonical = _canonical_payload(je, lines)
        je.entry_hash = hashlib.sha256((je.prev_hash + canonical).encode("utf-8")).hexdigest()
        
        session.add(je)
        
        tl1 = TransactionLine(
            id=line1_id,
            journal_entry_id=entry_id,
            account_code="1000",
            account_name="Cash",
            debit=Decimal("100.00"),
            credit=Decimal("0.00"),
            currency="USD",
            base_amount=Decimal("100.00"),
        )
        tl2 = TransactionLine(
            id=line2_id,
            journal_entry_id=entry_id,
            account_code="4000",
            account_name="Revenue",
            debit=Decimal("0.00"),
            credit=Decimal("100.00"),
            currency="USD",
            base_amount=Decimal("100.00"),
        )
        session.add_all([tl1, tl2])
        await session.commit()

    return tenant_id


@pytest.mark.asyncio
async def test_invariants_pass_healthy_ledger(tenant_session_factory, seeded_tenant):
    """
    Given a mathematically and cryptographically sound ledger,
    the Invariant framework must return PASS.
    """
    async with tenant_session_factory() as session:
        run = await run_all_invariants(session, seeded_tenant)
        assert run.status == ReconciliationStatus.PASS
        assert run.failed_checks is None


@pytest.mark.asyncio
async def test_invariants_catch_unbalanced_entry(tenant_engine, tenant_session_factory, seeded_tenant):
    """
    If a journal entry is unbalanced (e.g. via direct SQL manipulation),
    the Invariant framework must return FAIL and list the unbalanced entry.
    """
    # 1. Corrupt the database
    async with tenant_engine.begin() as conn:
        await conn.execute(text("UPDATE tenant.transaction_lines SET debit = 999.99 WHERE account_code = '1000'"))
        
    # 2. Run invariants
    async with tenant_session_factory() as session:
        run = await run_all_invariants(session, seeded_tenant)
        
        assert run.status == ReconciliationStatus.FAIL
        assert len(run.failed_checks) > 0
        
        check_names = [c["check"] for c in run.failed_checks]
        assert "ledger_balance" in check_names
        assert "hash_chain" in check_names


@pytest.mark.asyncio
async def test_invariants_catch_hash_chain_corruption(tenant_engine, tenant_session_factory, seeded_tenant):
    """
    If the cryptographic hash chain is altered (e.g. an attacker tries to change prev_hash),
    the framework must detect the tamper and FAIL.
    """
    # 1. Corrupt the database
    async with tenant_engine.begin() as conn:
        await conn.execute(text("UPDATE tenant.journal_entries SET prev_hash = '1' || SUBSTRING(prev_hash, 2)"))
        
    # 2. Run invariants
    async with tenant_session_factory() as session:
        run = await run_all_invariants(session, seeded_tenant)
        
        assert run.status == ReconciliationStatus.FAIL
        assert len(run.failed_checks) == 1
        assert run.failed_checks[0]["check"] == "hash_chain"


@pytest.mark.asyncio
async def test_invariants_catch_stale_outbox(tenant_session_factory, public_engine, seeded_tenant):
    """
    If an outbox event is older than 5 minutes and not published,
    the framework must detect the failure.
    """
    # 1. Corrupt the database
    async with public_engine.begin() as conn:
        await conn.execute(
            text("UPDATE public.outbox_events SET occurred_at = NOW() - INTERVAL '10 minutes'"),
        )
        
    # 2. Run invariants
    async with tenant_session_factory() as session:
        run = await run_all_invariants(session, seeded_tenant)
        
        assert run.status == ReconciliationStatus.FAIL
        assert len(run.failed_checks) == 1
        assert run.failed_checks[0]["check"] == "outbox_health"
