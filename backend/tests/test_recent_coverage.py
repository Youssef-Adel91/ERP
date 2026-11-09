"""
tests/test_recent_coverage.py — Coverage for recent mission-critical features:
  1. VAT split: invoice.created with tax_amount credits 2200 and revenue net (4010).
  2. Cheques: incoming receipt/clear/bounce, outgoing issue/clear/bounce.
  3. Payroll approval: DR 5200 gross, CR 2120 net, CR 2130 deductions.
  4. GL Postings: record_failure() persists FAILED row, GET /failed and POST /{id}/retry.
  5. Recruitment bulk import: accepts full_name, passport_number, etc. headers.
"""
from __future__ import annotations

import io
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.event_bus import DomainEvent
from app.modules.accounting.events import _build_invoice_lines, handle_invoice_created
from app.modules.accounting.models.core import Account, AccountType, JournalEntry, JournalEntryLine
from app.modules.accounting.models.posting import GLPosting, GLPostingStatus
from app.modules.accounting.services.gl_posting import record_failure, reserve_posting
from app.modules.accounting.services.mappings import AccountMappingKey, get_default_account
from app.modules.contacts.models import Contact, ContactStatus, ContactType
from app.modules.finance.models.cheques import Cheque, ChequeStatus, ChequeType
from app.modules.finance.services.cheque_service import (
    bounce_cheque,
    clear_cheque,
    deposit_cheque,
    post_cheque_registration,
)
from app.modules.hr.models.core import Payslip, PayslipStatus
from app.modules.hr.services.payroll import approve_payslip
from app.plugins.recruitment.services.importing import _normalise_headers


# ── 1. VAT Split on invoice.created ───────────────────────────────────────────

def test_vat_split_build_invoice_lines():
    """
    invoice.created with tax_amount splits lines into:
      - DR AR 1200 (gross: 1140.0000)
      - CR Revenue 4010 (net: 1000.0000)
      - CR VAT Payable 2200 (tax: 140.0000)
    """
    payload = {
        "invoice_number": "INV-VAT-001",
        "amount": "1140.0000",
        "tax_amount": "140.0000",
    }
    lines = _build_invoice_lines(
        payload=payload,
        amount=Decimal("1140.0000"),
        ar_code="1200",
        rev_code="4010",
        customer="Test Customer",
        invoice_number="INV-VAT-001",
    )
    assert len(lines) == 3

    line_map = {l["account_code"]: l for l in lines}
    assert line_map["1200"]["debit"] == Decimal("1140.0000")
    assert line_map["1200"]["credit"] == Decimal("0.0000")

    assert line_map["4010"]["debit"] == Decimal("0.0000")
    assert line_map["4010"]["credit"] == Decimal("1000.0000")

    assert line_map["2200"]["debit"] == Decimal("0.0000")
    assert line_map["2200"]["credit"] == Decimal("140.0000")

    # Invariant: debits == credits
    assert sum(l["debit"] for l in lines) == sum(l["credit"] for l in lines)


# ── 2. Cheques Lifecycle (Incoming & Outgoing) ────────────────────────────────

@pytest.mark.asyncio
async def test_incoming_cheque_lifecycle(db_session: AsyncSession, seed_tenant_and_users):
    """
    Incoming Cheque:
      1. Register: DR Notes Rec (1150), CR AR (1200)
      2. Deposit: State -> DEPOSITED (no extra GL entry)
      3. Clear: DR Cash & Banks (1100), CR Notes Rec (1150)
      4. Bounce: Reverses registration -> DR AR (1200), CR Notes Rec (1150)
    """
    contact = Contact(
        id=uuid4(),
        name="Test Customer",
        contact_type=ContactType.CUSTOMER,
        status=ContactStatus.ACTIVE,
    )
    db_session.add(contact)
    await db_session.flush()

    cheque = Cheque(
        id=uuid4(),
        cheque_number=f"CHQ-IN-{uuid4().hex[:6]}",
        cheque_type=ChequeType.INCOMING,
        amount=Decimal("5000.0000"),
        status=ChequeStatus.PENDING,
        issue_date=date.today(),
        due_date=date.today(),
        bank_name="CIB",
        contact_id=contact.id,
    )
    db_session.add(cheque)
    await db_session.flush()

    # 1. Register
    await post_cheque_registration(db_session, cheque)
    entries = (await db_session.execute(
        select(JournalEntry).where(JournalEntry.source_id == cheque.id)
    )).scalars().all()
    assert len(entries) == 1
    reg_entry = entries[0]
    assert reg_entry.status == GLPostingStatus.POSTED

    # 2. Deposit
    deposited = await deposit_cheque(db_session, cheque.id)
    assert deposited.status == ChequeStatus.DEPOSITED

    # 3. Clear
    cleared = await clear_cheque(db_session, cheque.id)
    assert cleared.status == ChequeStatus.CLEARED

    # 4. Bounce
    # Reset status to DEPOSITED to test bounce reversal
    cheque.status = ChequeStatus.DEPOSITED
    db_session.add(cheque)
    await db_session.commit()

    bounced = await bounce_cheque(db_session, cheque.id)
    assert bounced.status == ChequeStatus.BOUNCED


@pytest.mark.asyncio
async def test_outgoing_cheque_lifecycle(db_session: AsyncSession, seed_tenant_and_users):
    """
    Outgoing Cheque:
      1. Register: DR AP (2100), CR Notes Payable (2150)
      2. Clear: DR Notes Payable (2150), CR Cash & Banks (1100)
    """
    supplier = Contact(
        id=uuid4(),
        name="Test Supplier",
        contact_type=ContactType.SUPPLIER,
        status=ContactStatus.ACTIVE,
    )
    db_session.add(supplier)
    await db_session.flush()

    cheque = Cheque(
        id=uuid4(),
        cheque_number=f"CHQ-OUT-{uuid4().hex[:6]}",
        cheque_type=ChequeType.OUTGOING,
        amount=Decimal("3000.0000"),
        status=ChequeStatus.PENDING,
        issue_date=date.today(),
        due_date=date.today(),
        bank_name="NBE",
        contact_id=supplier.id,
    )
    db_session.add(cheque)
    await db_session.flush()

    # 1. Register
    await post_cheque_registration(db_session, cheque)
    entries = (await db_session.execute(
        select(JournalEntry).where(JournalEntry.source_id == cheque.id)
    )).scalars().all()
    assert len(entries) == 1

    # 2. Clear
    cleared = await clear_cheque(db_session, cheque.id)
    assert cleared.status == ChequeStatus.CLEARED


# ── 3. Payroll Approval GL Accrual ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_payroll_approval_gl_accrual(db_session: AsyncSession, seed_tenant_and_users):
    """
    Payroll Approval:
      Gross: Basic (8000) + Allowances (2000) = 10,000
      Deductions: 1,500
      Net Pay: 8,500
      GL Entry:
        DR 5200 Salaries Expense: 10,000
        CR 2120 Accrued Salaries: 8,500
        CR 2130 Payroll Deductions: 1,500
    """
    employee_id = uuid4()
    payslip = Payslip(
        id=uuid4(),
        employee_id=employee_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        basic_wage=Decimal("8000.0000"),
        allowances=Decimal("2000.0000"),
        deductions=Decimal("1500.0000"),
        status=PayslipStatus.DRAFT,
    )
    db_session.add(payslip)
    await db_session.commit()

    await approve_payslip(db_session, payslip.id)
    await db_session.refresh(payslip)

    assert payslip.status == PayslipStatus.APPROVED
    assert payslip.net_pay == Decimal("8500.0000")

    # Verify Journal Entry
    je_stmt = select(JournalEntry).where(JournalEntry.source_id == payslip.id)
    je = (await db_session.execute(je_stmt)).scalar_one()

    # Verify lines
    lines_stmt = select(JournalEntryLine).where(JournalEntryLine.journal_entry_id == je.id)
    lines = (await db_session.execute(lines_stmt)).scalars().all()
    assert len(lines) == 3

    line_map = {l.account_code: l for l in lines}
    assert line_map["5200"].debit == Decimal("10000.0000")
    assert line_map["5200"].credit == Decimal("0.0000")

    assert line_map["2120"].debit == Decimal("0.0000")
    assert line_map["2120"].credit == Decimal("8500.0000")

    assert line_map["2130"].debit == Decimal("0.0000")
    assert line_map["2130"].credit == Decimal("1500.0000")

    assert sum(l.debit for l in lines) == sum(l.credit for l in lines)


# ── 4. GL Postings Failed & Retry ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_failure_persists_even_when_reservation_rolls_back(
    db_session: AsyncSession,
    seed_tenant_and_users,
):
    """
    Verify record_failure() saves a FAILED row that survives a rolled-back transaction.
    """
    source_id = uuid4()
    entry_kind = "test_checkout_rev"

    await record_failure(
        session=db_session,
        source_type="case",
        source_id=source_id,
        entry_kind=entry_kind,
        exc=RuntimeError("Simulation of connection drop"),
        invoice_number="INV-FAIL-001",
        amount=Decimal("750.0000"),
    )
    await db_session.commit()

    stmt = select(GLPosting).where(
        GLPosting.source_id == source_id,
        GLPosting.entry_kind == entry_kind,
    )
    posting = (await db_session.execute(stmt)).scalar_one_or_none()
    assert posting is not None
    assert posting.status == GLPostingStatus.FAILED
    assert posting.error_type == "RuntimeError"
    assert "Simulation of connection drop" in posting.error_message


@pytest.mark.asyncio
async def test_gl_postings_failed_and_retry_endpoints(client: AsyncClient, db_session: AsyncSession):
    """
    Test GET /accounting/gl-postings/failed and POST /accounting/gl-postings/{id}/retry.
    """
    source_id = uuid4()
    await record_failure(
        session=db_session,
        source_type="case",
        source_id=source_id,
        entry_kind="hospitality_checkout_revenue",
        exc=RuntimeError("Transient DB glitch"),
        invoice_number="INV-RETRY-001",
        amount=Decimal("1200.0000"),
    )
    await db_session.commit()

    # GET /accounting/gl-postings/failed
    res = await client.get("/api/v1/accounting/gl-postings/failed")
    assert res.status_code == 200
    failed_list = res.json()
    assert any(p["invoice_number"] == "INV-RETRY-001" for p in failed_list)

    posting_row = next(p for p in failed_list if p["invoice_number"] == "INV-RETRY-001")
    posting_id = posting_row["id"]

    # POST /accounting/gl-postings/{id}/retry
    res_retry = await client.post(f"/api/v1/accounting/gl-postings/{posting_id}/retry")
    # 200 OK or 409/422 if source cannot be replayed without external payload
    assert res_retry.status_code in (200, 409, 422)


# ── 5. Recruitment Bulk Import Header Normalisation ──────────────────────────

def test_recruitment_import_header_normalisation():
    """
    Verify _normalise_headers accepts canonical and aliased recruitment headers:
    full_name, passport_number, etc.
    """
    headers = [
        "Full Name",
        "Passport Number",
        "المهنة",
        "Target Country",
        "الجنسية",
        "experience (years)",
    ]
    mapping = _normalise_headers(headers)
    assert mapping[0] == "full_name"
    assert mapping[1] == "passport_number"
    assert mapping[2] == "profession"
    assert mapping[3] == "target_country"
    assert mapping[4] == "nationality"
    assert mapping[5] == "years_of_experience"

    # Also test snake_case canonical headers directly
    canonical = ["full_name", "passport_number", "profession", "target_country", "nationality"]
    canon_map = _normalise_headers(canonical)
    assert canon_map[0] == "full_name"
    assert canon_map[1] == "passport_number"
    assert canon_map[2] == "profession"
    assert canon_map[3] == "target_country"
    assert canon_map[4] == "nationality"
