"""
app/modules/hr/services/payroll.py — Payroll to GL Engine
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models.core import Payslip, PayslipStatus
from app.modules.accounting.models.core import JournalEntry, JournalEntryLine, JournalEntryStatus, Account


async def approve_payslip(session: AsyncSession, payslip_id: UUID) -> None:
    """
    Mathematically calculates net pay and atomically posts a Journal Entry to the GL.
    Wraps the payslip in a .with_for_update() row-level lock to prevent double posting.
    """
    # 1. Fetch payslip with lock
    result = await session.execute(
        select(Payslip).where(Payslip.id == payslip_id).with_for_update()
    )
    payslip = result.scalar_one_or_none()
    
    if not payslip:
        raise HTTPException(status_code=404, detail="Payslip not found")
        
    if payslip.status != PayslipStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only DRAFT payslips can be approved")
        
    # 2. Calculate final net pay mathematically
    payslip.net_pay = payslip.basic_wage + payslip.allowances - payslip.deductions
    payslip.status = PayslipStatus.APPROVED
    session.add(payslip)
    
    if payslip.net_pay <= 0:
        # Don't post empty or negative journal entries
        return
    
    # 3. Post to General Ledger
    # For MVP, assuming 5100 = Operating/Salaries Expense, 2100 = Accounts Payable / Liability
    exp_acc = await session.scalar(select(Account).where(Account.code == "5100"))
    liab_acc = await session.scalar(select(Account).where(Account.code == "2100"))
    
    if not exp_acc or not liab_acc:
        raise HTTPException(
            status_code=500, 
            detail="Required GL accounts (5100, 2100) not found in Chart of Accounts."
        )
        
    je = JournalEntry(
        reference=f"PAYSLIP-{str(payslip_id)[:8].upper()}",
        reference_id=payslip_id,
        entry_date=date.today(),
        description=f"Payroll approval for period {payslip.period_start} to {payslip.period_end}",
        status=JournalEntryStatus.POSTED,
        source_type="PAYROLL",
        source_id=payslip_id,
    )
    session.add(je)
    await session.flush() # Ensures we get je.id
    
    session.add_all([
        JournalEntryLine(
            journal_entry_id=je.id,
            account_id=exp_acc.id,
            account_code=exp_acc.code,
            debit=payslip.net_pay,
            credit=Decimal("0.0"),
            description="Salaries Expense"
        ),
        JournalEntryLine(
            journal_entry_id=je.id,
            account_id=liab_acc.id,
            account_code=liab_acc.code,
            debit=Decimal("0.0"),
            credit=payslip.net_pay,
            description="Accrued Salaries Payable"
        )
    ])
