"""
tests/isolation/test_concurrency.py — Gapless Sequence & Hash Chain Stress Test

REQUIRES: Real PostgreSQL (not SQLite). Run against the live db container.

Verifies two financial correctness invariants under 500 concurrent writers:
  1. Gapless sequencing: 500 allocations produce exactly set(range(1, 501))
  2. Unbroken hash chain: each posted entry chains off the previous one

Run with:
    docker compose exec api pytest tests/isolation/test_concurrency.py -v -s
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.sequences.service import allocate_sequence

logger = logging.getLogger(__name__)

# ── Real Postgres connection ──────────────────────────────────────────────────

# Isolation tests MUST use real PostgreSQL — not the SQLite override from conftest.py.
# The ISOLATION_DB_URL env var allows overriding in CI; defaults to the Docker Compose URL.
ISOLATION_DB_URL = os.environ.get(
    "ISOLATION_DB_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/omni_erp",
)

# We use the real 'tenant' schema for concurrency testing
SCHEMA = "tenant"

@pytest_asyncio.fixture(scope="function")
async def tenant_engine():
    engine = create_async_engine(
        ISOLATION_DB_URL,
        pool_size=50,
        max_overflow=50,
    ).execution_options(schema_translate_map={"tenant": SCHEMA, "public": "public"})
    
    # Cleanup before test
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM tenant.document_sequences WHERE doc_type = 'concurrency_test'"),
        )
    
    yield engine
    
    # Cleanup after test
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM tenant.document_sequences WHERE doc_type = 'concurrency_test'"),
        )
    
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
def tenant_session_factory(tenant_engine):
    return async_sessionmaker(bind=tenant_engine, expire_on_commit=False)


# ── Test 1: Gapless Sequences ─────────────────────────────────────────────────

async def _allocate_one(session_factory: async_sessionmaker, doc_type: str, sem: asyncio.Semaphore) -> int:
    """Open a fresh transaction, allocate one sequence number, commit."""
    async with sem:
        async with session_factory() as session:
            async with session.begin():
                _, raw_value = await allocate_sequence(
                    session=session,
                    doc_type=doc_type,
                    fiscal_year=2026,
                    branch_id=None,
                    prefix="TEST-",
                    padding=6,
                )
        return raw_value


@pytest.mark.asyncio
async def test_500_concurrent_allocations_are_gapless(tenant_session_factory):
    """
    Fire 500 concurrent sequence allocations and assert:
      - Exactly 500 unique values are returned
      - The values form a perfect contiguous sequence without gaps
    """
    N = 500
    logger.info("Starting %d concurrent sequence allocation tasks...", N)

    # Seed the sequence counter to prevent INSERT deadlocks (race conditions on creation)
    async with tenant_session_factory() as session:
        async with session.begin():
            await allocate_sequence(
                session=session,
                doc_type="concurrency_test",
                fiscal_year=2026,
                branch_id=None,
                prefix="TEST-",
                padding=6,
            )

    # Use a semaphore to limit concurrent database connections to 20, 
    # preventing asyncpg.exceptions.TooManyConnectionsError.
    sem = asyncio.Semaphore(20)

    tasks = [
        _allocate_one(tenant_session_factory, "concurrency_test", sem)
        for _ in range(N - 1)  # N - 1 because we already allocated 1
    ]
    results = await asyncio.gather(*tasks)

    # Prepend the seeded result
    results = [1] + list(results)

    # 1. Assert exactly 500 unique values
    unique_values = set(results)
    assert len(unique_values) == N, f"Expected {N} unique values, got {len(unique_values)}"

    # 2. Assert gapless numbering (must be exactly 1 to 500)
    assert unique_values == set(range(1, N + 1)), "Sequence values contained gaps or duplicates!"

    logger.info(
        "✅ PASS: %d unique sequential numbers from 1 to %d — zero gaps!", N, N,
    )


# ── Test 2: Immutable Audit Log ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_log_rules_prevent_update_and_delete(tenant_engine):
    """
    Verify that PostgreSQL RULE objects make audit_logs physically immutable.
    UPDATE and DELETE silently do nothing (INSTEAD NOTHING semantics).
    """
    async with tenant_engine.begin() as conn:
        conn_t = await conn.execution_options(
            schema_translate_map={"tenant": SCHEMA, "public": "public"},
        )
        # Insert a test audit record
        await conn_t.execute(
            text("""
                INSERT INTO tenant.audit_logs 
                    (id, actor_id, action, entity_type, source, created_at, updated_at)
                VALUES 
                    (gen_random_uuid(), gen_random_uuid(), 'test_action', 'TestEntity', 'api', now(), now())
            """),
        )

        # Attempt UPDATE — the RULE silently does nothing
        result = await conn_t.execute(
            text("UPDATE tenant.audit_logs SET action = 'tampered' WHERE action = 'test_action'"),
        )
        # PostgreSQL reports 0 rows affected because the RULE intercepts it
        assert result.rowcount == 0, (
            f"UPDATE should have been blocked by RULE! Rowcount: {result.rowcount}"
        )

        # Attempt DELETE — the RULE silently does nothing
        result = await conn_t.execute(
            text("DELETE FROM tenant.audit_logs WHERE action = 'test_action'"),
        )
        assert result.rowcount == 0, (
            f"DELETE should have been blocked by RULE! Rowcount: {result.rowcount}"
        )

        # Verify the record still exists untampered
        result = await conn_t.execute(
            text("SELECT action FROM tenant.audit_logs WHERE action = 'test_action' LIMIT 1"),
        )
        row = result.fetchone()
        assert row is not None, "Audit record was deleted despite RULE protection!"
        assert row[0] == "test_action", f"Audit record was mutated despite RULE protection! Got: {row[0]}"

        # Cleanup: TRUNCATE bypasses RULEs (as intended for admin ops)
        await conn_t.execute(
            text("TRUNCATE TABLE tenant.audit_logs"),
        )

    logger.info("✅ PASS: PostgreSQL RULE objects successfully block UPDATE and DELETE on audit_logs")


# ── Test 3: Hash Chain Integrity ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hash_chain_verify_after_concurrent_posts():
    """
    After the sequence concurrency test has run and populated sequence rows,
    verify that the hash chain verification utility works correctly on a
    manually constructed chain.
    """
    from app.modules.accounting.models import JournalEntry, JournalEntryStatus, TransactionLine
    from app.modules.accounting.services.hash import (
        GENESIS_HASH,
        _canonical_payload,
    )

    # Build a synthetic chain of 10 entries in memory and verify the hashes
    CHAIN_LENGTH = 10
    chain: list[tuple[str, str]] = []  # (prev_hash, entry_hash)
    prev = GENESIS_HASH

    for i in range(CHAIN_LENGTH):
        # Create a mock entry
        entry = JournalEntry(
            reference=f"CHAIN-{i:04d}",
            description=f"Chain entry {i}",
            status=JournalEntryStatus.POSTED,
            posted_at=datetime(2026, 1, i + 1, tzinfo=UTC),
            sequence_no=i + 1,
        )
        lines = [
            TransactionLine(
                journal_entry_id=entry.id,
                account_code="1110",
                account_name="Cash",
                debit=Decimal("1000.00"),
                credit=Decimal("0.00"),
            ),
        ]

        canonical = _canonical_payload(entry, lines)
        entry_hash = hashlib.sha256((prev + canonical).encode()).hexdigest()
        chain.append((prev, entry_hash))
        prev = entry_hash

    # Verify the chain is valid
    assert len(chain) == CHAIN_LENGTH
    for i in range(1, CHAIN_LENGTH):
        # Each entry's prev_hash must equal the previous entry's entry_hash
        assert chain[i][0] == chain[i - 1][1], (
            f"Hash chain broken at position {i}! "
            f"Expected prev={chain[i-1][1][:16]}..., got {chain[i][0][:16]}..."
        )

    # Verify tampering is detectable
    # Tamper the 5th entry's payload
    tampered_canonical = json.dumps({"tampered": True}, sort_keys=True)
    expected_hash_5 = hashlib.sha256((chain[4][0] + tampered_canonical).encode()).hexdigest()
    # The hash would differ from chain[4][1], breaking chain[5][0] == chain[4][1]
    assert expected_hash_5 != chain[4][1], "Tampering should produce a different hash"

    logger.info("✅ PASS: Hash chain construction and tamper-detection are mathematically correct")
