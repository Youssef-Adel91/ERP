"""
app/modules/finance/services/cheque_service.py — Cheque State Machine & Services
"""
import logging
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models.core import JournalEntry, JournalEntryStatus
from app.modules.accounting.services.journal import create_journal_entry
from app.modules.accounting.services.mappings import (
    AccountMappingKey,
    get_default_account_id,
)
from app.modules.finance.models.cheques import Cheque, ChequeStatus, ChequeType

logger = logging.getLogger(__name__)

# source_type tag used on the JournalEntry created when an incoming cheque is
# deposited, so bounce_cheque() can find it again to reverse it (same
# reference_id/source_type lookup idiom used by the accounting event
# consumers — see app/modules/accounting/consumers/events.py::_is_already_journaled).
_CHEQUE_DEPOSIT_SOURCE_TYPE = "finance.cheque_deposit"
_CHEQUE_BOUNCE_SOURCE_TYPE = "finance.cheque_bounce"


async def _find_journal_entry(
    db: AsyncSession, source_type: str, source_id: UUID,
) -> JournalEntry | None:
    """Look up a previously-created JournalEntry by (source_type, source_id)."""
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.source_type == source_type,
            JournalEntry.source_id == source_id,
        )
    )
    return result.scalars().first()


async def deposit_cheque(db: AsyncSession, cheque_id: UUID) -> Cheque:
    result = await db.execute(select(Cheque).where(Cheque.id == cheque_id))
    cheque = result.scalar_one_or_none()
    
    if not cheque:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Cheque not found"
        )
    
    if cheque.cheque_type != ChequeType.INCOMING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Only incoming cheques can be deposited"
        )
        
    if cheque.status != ChequeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot deposit cheque in {cheque.status} state. Expected pending."
        )

    # Record the accounting impact of the deposit: the cheque moves from a
    # promise-to-pay (Accounts Receivable) into the bank (Cash and Banks).
    # This entry is what bounce_cheque() below reverses if the cheque later
    # bounces — mirroring the same "swap debit/credit on the original
    # entry's lines" pattern used by
    # app.modules.accounting.service.create_reversing_entry().
    cash_id = await get_default_account_id(db, AccountMappingKey.CASH_AND_BANKS)
    ar_id = await get_default_account_id(db, AccountMappingKey.ACCOUNTS_RECEIVABLE)
    await create_journal_entry(
        session=db,
        description=f"Cheque Deposit — {cheque.cheque_number}",
        lines=[
            {
                "account_id": cash_id,
                "debit": cheque.amount,
                "credit": Decimal("0.0000"),
                "description": f"Cheque {cheque.cheque_number} deposited",
            },
            {
                "account_id": ar_id,
                "debit": Decimal("0.0000"),
                "credit": cheque.amount,
                "description": f"Cheque {cheque.cheque_number} deposited",
            },
        ],
        reference=f"CHQ-{cheque.cheque_number}",
        source_type=_CHEQUE_DEPOSIT_SOURCE_TYPE,
        source_id=cheque.id,
        status=JournalEntryStatus.POSTED,
    )

    cheque.status = ChequeStatus.DEPOSITED
    db.add(cheque)
    await db.commit()
    await db.refresh(cheque)
    return cheque


async def clear_cheque(db: AsyncSession, cheque_id: UUID) -> Cheque:
    result = await db.execute(select(Cheque).where(Cheque.id == cheque_id))
    cheque = result.scalar_one_or_none()
    
    if not cheque:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Cheque not found"
        )
        
    if cheque.cheque_type == ChequeType.INCOMING and cheque.status != ChequeStatus.DEPOSITED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Incoming cheque must be deposited before clearing. Current status: {cheque.status}"
        )
        
    if cheque.cheque_type == ChequeType.OUTGOING and cheque.status != ChequeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Outgoing cheque must be pending to clear. Current status: {cheque.status}"
        )
        
    cheque.status = ChequeStatus.CLEARED
    db.add(cheque)
    await db.commit()
    await db.refresh(cheque)
    return cheque


async def bounce_cheque(db: AsyncSession, cheque_id: UUID) -> Cheque:
    result = await db.execute(select(Cheque).where(Cheque.id == cheque_id))
    cheque = result.scalar_one_or_none()
    
    if not cheque:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Cheque not found"
        )
        
    if cheque.cheque_type == ChequeType.INCOMING and cheque.status != ChequeStatus.DEPOSITED:
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST, 
             detail=f"Incoming cheque must be deposited to bounce. Current status: {cheque.status}"
         )
         
    if cheque.cheque_type == ChequeType.OUTGOING and cheque.status != ChequeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outgoing cheque must be pending to bounce. Current status: {cheque.status}"
        )

    # A bounced INCOMING cheque means the deposit posted in deposit_cheque()
    # above never actually cleared the bank — the DR Cash / CR AR entry must
    # be reversed (mirrors app.modules.accounting.service.create_reversing_entry:
    # a brand-new entry with every line's debit/credit swapped, posted
    # immediately since this is an automated system-generated correction,
    # same as the sales.credit_note_posted reversal of sales.invoice_posted
    # in app/modules/accounting/consumers/events.py).
    if cheque.cheque_type == ChequeType.INCOMING:
        deposit_entry = await _find_journal_entry(
            db, _CHEQUE_DEPOSIT_SOURCE_TYPE, cheque.id,
        )
        if deposit_entry is None:
            logger.warning(
                "Bouncing cheque %s (%s) but no deposit JournalEntry (source_type=%s) "
                "was found to reverse — proceeding with status change only.",
                cheque.id, cheque.cheque_number, _CHEQUE_DEPOSIT_SOURCE_TYPE,
            )
        else:
            already_reversed = await _find_journal_entry(
                db, _CHEQUE_BOUNCE_SOURCE_TYPE, cheque.id,
            )
            if already_reversed is None:
                await create_journal_entry(
                    session=db,
                    description=f"Cheque Bounce Reversal — {cheque.cheque_number}",
                    lines=[
                        {
                            "account_id": line.account_id,
                            "debit": line.credit,   # Swap debit <-> credit
                            "credit": line.debit,   # Swap debit <-> credit
                            "description": f"[BOUNCE REVERSAL] {line.description or ''}".strip(),
                        }
                        for line in deposit_entry.lines
                    ],
                    reference=f"CHQ-BOUNCE-{cheque.cheque_number}",
                    source_type=_CHEQUE_BOUNCE_SOURCE_TYPE,
                    source_id=cheque.id,
                    status=JournalEntryStatus.POSTED,
                )

    cheque.status = ChequeStatus.BOUNCED
    db.add(cheque)
    await db.commit()
    await db.refresh(cheque)
    return cheque
