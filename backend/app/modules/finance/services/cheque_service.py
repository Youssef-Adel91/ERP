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
_CHEQUE_RECEIPT_SOURCE_TYPE = "finance.cheque_receipt"      # incoming: DR Notes Rec / CR AR
_CHEQUE_ISSUE_SOURCE_TYPE = "finance.cheque_issue"          # outgoing: DR AP / CR Notes Pay
_CHEQUE_CLEAR_SOURCE_TYPE = "finance.cheque_clear"          # DR Cash / CR Notes (or reverse for outgoing)

# Accounting policy (standard Egyptian practice — أوراق قبض / أوراق دفع):
#   Incoming  receipt : DR Notes Receivable (1150)   CR Accounts Receivable (1200)
#             deposit : no GL entry (still a note under collection)
#             clear   : DR Cash & Banks (1100)       CR Notes Receivable (1150)
#             bounce  : DR Accounts Receivable       CR Notes Receivable   (customer owes again)
#   Outgoing  issue   : DR Accounts Payable (2100)  CR Notes Payable (2150)
#             clear   : DR Notes Payable             CR Cash & Banks
#             bounce  : DR Notes Payable             CR Accounts Payable   (supplier unpaid again)


async def _post_cheque_entry(
    db: AsyncSession,
    cheque: Cheque,
    *,
    source_type: str,
    reference_prefix: str,
    description: str,
    debit_key: AccountMappingKey,
    credit_key: AccountMappingKey,
) -> None:
    """Post a balanced two-line entry for a cheque event, once per (type, cheque)."""
    if await _find_journal_entry(db, source_type, cheque.id) is not None:
        return
    debit_id = await get_default_account_id(db, debit_key)
    credit_id = await get_default_account_id(db, credit_key)
    note = f"Cheque {cheque.cheque_number}"
    await create_journal_entry(
        session=db,
        description=f"{description} — {cheque.cheque_number}",
        lines=[
            {"account_id": debit_id, "debit": cheque.amount, "credit": Decimal("0.0000"), "description": note},
            {"account_id": credit_id, "debit": Decimal("0.0000"), "credit": cheque.amount, "description": note},
        ],
        reference=f"{reference_prefix}-{cheque.cheque_number}",
        source_type=source_type,
        source_id=cheque.id,
        status=JournalEntryStatus.POSTED,
    )


async def post_cheque_registration(db: AsyncSession, cheque: Cheque) -> None:
    """Called when a cheque is first recorded (incoming receipt / outgoing issue)."""
    if cheque.cheque_type == ChequeType.INCOMING:
        await _post_cheque_entry(
            db, cheque, source_type=_CHEQUE_RECEIPT_SOURCE_TYPE, reference_prefix="CHQ-RCV",
            description="Cheque Received",
            debit_key=AccountMappingKey.NOTES_RECEIVABLE, credit_key=AccountMappingKey.ACCOUNTS_RECEIVABLE,
        )
    else:
        await _post_cheque_entry(
            db, cheque, source_type=_CHEQUE_ISSUE_SOURCE_TYPE, reference_prefix="CHQ-ISS",
            description="Cheque Issued",
            debit_key=AccountMappingKey.ACCOUNTS_PAYABLE, credit_key=AccountMappingKey.NOTES_PAYABLE,
        )


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

    # Deposit is a custody change only: the cheque is still a note under
    # collection (1150). Cash is recognised when the bank clears it.
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
        
    if cheque.cheque_type == ChequeType.INCOMING:
        await _post_cheque_entry(
            db, cheque, source_type=_CHEQUE_CLEAR_SOURCE_TYPE, reference_prefix="CHQ-CLR",
            description="Cheque Cleared",
            debit_key=AccountMappingKey.CASH_AND_BANKS, credit_key=AccountMappingKey.NOTES_RECEIVABLE,
        )
    else:
        await _post_cheque_entry(
            db, cheque, source_type=_CHEQUE_CLEAR_SOURCE_TYPE, reference_prefix="CHQ-CLR",
            description="Cheque Cleared",
            debit_key=AccountMappingKey.NOTES_PAYABLE, credit_key=AccountMappingKey.CASH_AND_BANKS,
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

    # Bounce = reverse the registration entry (receipt for incoming, issue for
    # outgoing) so the customer/supplier balance is restored. Legacy tenants
    # that posted a deposit entry instead are reversed through that entry.
    reg_type = (
        _CHEQUE_RECEIPT_SOURCE_TYPE
        if cheque.cheque_type == ChequeType.INCOMING
        else _CHEQUE_ISSUE_SOURCE_TYPE
    )
    original = await _find_journal_entry(db, reg_type, cheque.id)
    if original is None and cheque.cheque_type == ChequeType.INCOMING:
        original = await _find_journal_entry(db, _CHEQUE_DEPOSIT_SOURCE_TYPE, cheque.id)
    if original is None:
        logger.warning(
            "Bouncing cheque %s (%s) but no registration JournalEntry found to reverse — "
            "proceeding with status change only.", cheque.id, cheque.cheque_number,
        )
    elif await _find_journal_entry(db, _CHEQUE_BOUNCE_SOURCE_TYPE, cheque.id) is None:
        await create_journal_entry(
            session=db,
            description=f"Cheque Bounce Reversal — {cheque.cheque_number}",
            lines=[
                {
                    "account_id": line.account_id,
                    "debit": line.credit,
                    "credit": line.debit,
                    "description": f"[BOUNCE REVERSAL] {line.description or ''}".strip(),
                }
                for line in original.lines
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
