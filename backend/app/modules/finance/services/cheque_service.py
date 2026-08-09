"""
app/modules/finance/services/cheque_service.py — Cheque State Machine & Services
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.models.cheques import Cheque, ChequeStatus, ChequeType


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
        
    cheque.status = ChequeStatus.BOUNCED
    db.add(cheque)
    await db.commit()
    await db.refresh(cheque)
    return cheque
