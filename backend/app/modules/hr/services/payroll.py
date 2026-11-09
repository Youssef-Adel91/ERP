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
    
    # 3. Post to General Ledger — standard payroll accrual:
    #    DR Salaries Expense (gross = basic + allowances)
    #    CR Accrued Salaries Payable (net pay owed to the employee)
    #    CR Payroll Deductions Payable (insurance / tax withheld, owed to authorities)
    from app.modules.accounting.services.mappings import (
        AccountMappingKey,
        get_default_account,
    )

    exp_acc = await get_default_account(session, AccountMappingKey.SALARIES_EXPENSE)
    pay_acc = await get_default_account(session, AccountMappingKey.SALARIES_PAYABLE)
    gross = payslip.basic_wage + payslip.allowances
    deductions = payslip.deductions or Decimal("0.0")

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
    await session.flush()  # Ensures we get je.id

    lines = [
        JournalEntryLine(
            journal_entry_id=je.id,
            account_id=exp_acc.id,
            account_code=exp_acc.code,
            account_name=exp_acc.name_ar or exp_acc.name,
            debit=gross,
            credit=Decimal("0.0"),
            description="Salaries Expense (gross)",
        ),
        JournalEntryLine(
            journal_entry_id=je.id,
            account_id=pay_acc.id,
            account_code=pay_acc.code,
            account_name=pay_acc.name_ar or pay_acc.name,
            debit=Decimal("0.0"),
            credit=payslip.net_pay,
            description="Accrued Salaries Payable (net)",
        ),
    ]
    if deductions > 0:
        ded_acc = await get_default_account(session, AccountMappingKey.PAYROLL_DEDUCTIONS_PAYABLE)
        lines.append(
            JournalEntryLine(
                journal_entry_id=je.id,
                account_id=ded_acc.id,
                account_code=ded_acc.code,
                account_name=ded_acc.name_ar or ded_acc.name,
                debit=Decimal("0.0"),
                credit=deductions,
                description="Payroll deductions withheld",
            )
        )
    session.add_all(lines)
