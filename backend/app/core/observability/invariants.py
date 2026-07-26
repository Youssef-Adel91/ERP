import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.models import ReconciliationRun, ReconciliationStatus

logger = logging.getLogger(__name__)

async def _check_ledger_balance(session: AsyncSession) -> dict | None:
    """
    Check 1: Ledger Balance.
    Ensures that for every journal entry, SUM(debit) == SUM(credit).
    """
    query = text("""
        SELECT journal_entry_id, SUM(debit) as total_debit, SUM(credit) as total_credit
        FROM tenant.transaction_lines
        GROUP BY journal_entry_id
        HAVING SUM(debit) != SUM(credit)
    """)
    result = await session.execute(query)
    unbalanced = result.fetchall()
    
    if unbalanced:
        details = [
            {
                "journal_entry_id": str(row.journal_entry_id),
                "total_debit": float(row.total_debit),
                "total_credit": float(row.total_credit),
            }
            for row in unbalanced
        ]
        return {"check": "ledger_balance", "errors": details}
    return None

async def _check_hash_chain(session: AsyncSession) -> dict | None:
    """
    Check 2: Hash Chain Verification.
    Re-verifies that the `entry_hash` of entry N-1 matches the `prev_hash` of entry N,
    and that `entry_hash` was calculated correctly.
    """
    import hashlib

    from app.modules.accounting.services.hash import _canonical_payload
    
    query = text("""
        SELECT 
            je.id, 
            je.sequence_no, 
            je.reference, 
            je.status, 
            je.entry_hash, 
            je.prev_hash,
            je.posted_at,
            COALESCE(
                json_agg(
                    json_build_object(
                        'account_code', tl.account_code,
                        'debit', tl.debit,
                        'credit', tl.credit
                    ) ORDER BY tl.account_code
                ) FILTER (WHERE tl.id IS NOT NULL),
                '[]'
            ) as lines
        FROM tenant.journal_entries je
        LEFT JOIN tenant.transaction_lines tl ON je.id = tl.journal_entry_id
        GROUP BY je.id
        ORDER BY je.sequence_no ASC
    """)
    result = await session.execute(query)
    entries = result.fetchall()
    
    errors = []
    expected_prev_hash = "0" * 64
    
    for row in entries:
        seq = row.sequence_no
        prev = row.prev_hash
        current_hash = row.entry_hash
        lines_data = row.lines
        
        if prev != expected_prev_hash:
            errors.append({
                "journal_entry_id": str(row.id),
                "sequence_no": seq,
                "error": "prev_hash mismatch",
                "expected_prev_hash": expected_prev_hash,
                "actual_prev_hash": prev,
            })
            expected_prev_hash = current_hash
            continue
            
        from decimal import Decimal
        reconstructed_lines = []
        for raw_line in lines_data:
            class MockLine:
                account_code = raw_line['account_code']
                debit = Decimal(str(raw_line['debit']))
                credit = Decimal(str(raw_line['credit']))
            reconstructed_lines.append(MockLine())
        
        class MockEntry:
            id = row.id
            sequence_no = seq
            reference = row.reference
            status = row.status
            posted_at = row.posted_at
            branch_id = None # Mock if required
        
        canonical = _canonical_payload(MockEntry(), reconstructed_lines)
        calculated_hash = hashlib.sha256((prev + canonical).encode("utf-8")).hexdigest()
        
        if calculated_hash != current_hash:
            errors.append({
                "journal_entry_id": str(row.id),
                "sequence_no": seq,
                "error": "entry_hash corrupted",
                "expected_hash": calculated_hash,
                "actual_hash": current_hash,
            })
            
        expected_prev_hash = current_hash
        
    if errors:
        return {"check": "hash_chain", "errors": errors}
    return None

async def _check_outbox_health(session: AsyncSession) -> dict | None:
    """
    Check 3: Outbox Health.
    Query `public.outbox_events` to ensure no event is stuck for > 5 minutes.
    """
    query = text("""
        SELECT id, occurred_at 
        FROM public.outbox_events 
        WHERE published_at IS NULL 
          AND occurred_at < NOW() - INTERVAL '5 minutes'
    """)
    result = await session.execute(query)
    stale_events = result.fetchall()
    
    if stale_events:
        details = [
            {"outbox_event_id": str(row.id), "occurred_at": str(row.occurred_at)}
            for row in stale_events
        ]
        return {"check": "outbox_health", "errors": details}
    return None


async def run_all_invariants(session: AsyncSession, tenant_id: UUID) -> ReconciliationRun:
    """
    Executes the full suite of invariants to ensure the ledger and outbox are mathematically and cryptographically sound.
    """
    logger.info(f"Starting Invariant Reconciliation Run for tenant {tenant_id}")
    
    failed_checks = []
    
    res1 = await _check_ledger_balance(session)
    if res1: failed_checks.append(res1)
        
    res2 = await _check_hash_chain(session)
    if res2: failed_checks.append(res2)
        
    res3 = await _check_outbox_health(session)
    if res3: failed_checks.append(res3)
        
    status = ReconciliationStatus.FAIL if failed_checks else ReconciliationStatus.PASS
    
    run_record = ReconciliationRun(
        status=status,
        failed_checks=failed_checks if failed_checks else None,
    )
    
    session.add(run_record)
    await session.commit()
    await session.refresh(run_record)
    
    if status == ReconciliationStatus.FAIL:
        logger.error(f"ReconciliationRun {run_record.id} FAILED for tenant {tenant_id}: {json.dumps(failed_checks)}")
    else:
        logger.info(f"ReconciliationRun {run_record.id} PASSED for tenant {tenant_id}")
        
    return run_record
