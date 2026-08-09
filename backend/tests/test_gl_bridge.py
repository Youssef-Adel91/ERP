"""
tests/test_gl_bridge.py — Integration Tests for Automated GL Bridge (Phase 3 Step 2)

Tests:
  1. Default GL Account Mappings resolution & automatic scaffolding (mappings.py)
  2. sales.invoice_posted consumer -> balanced DR Accounts Receivable, CR Revenue, CR Tax Payable
  3. sales.credit_note_posted consumer -> balanced CR Accounts Receivable, DR Revenue, DR Tax Payable
  4. inventory.stock_take_posted consumer -> balanced DR/CR Inventory Asset vs Stock Variance Expense
  5. Transaction Safety & Idempotency -> repeated events never duplicate journal entries
  6. Zero-tax invoice handling & zero-variance stock take skip logic
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.event_bus import DomainEvent
from app.modules.accounting.consumers.events import (
    handle_credit_note_posted,
    handle_invoice_posted,
    handle_stock_take_posted,
)
from app.modules.accounting.models import Account, AccountType, JournalEntry, JournalEntryStatus
from app.modules.accounting.services.mappings import (
    AccountMappingKey,
    get_default_account,
    resolve_default_accounts,
)


@pytest.mark.asyncio
class TestGLBridge:
    """Integration test suite for the Automated General Ledger Bridge."""

    async def test_default_account_mappings_scaffolding(
        self,
        db_session: AsyncSession,
        seed_tenant_and_users,
    ):
        """Verify that default GL accounts are automatically scaffolded and idempotent."""
        keys = [
            AccountMappingKey.ACCOUNTS_RECEIVABLE,
            AccountMappingKey.SALES_REVENUE,
            AccountMappingKey.SALES_TAX_PAYABLE,
            AccountMappingKey.INVENTORY_ASSET,
            AccountMappingKey.STOCK_VARIANCE_EXPENSE,
        ]

        resolved = await resolve_default_accounts(db_session, keys)
        assert len(resolved) == 5

        ar_account = resolved[AccountMappingKey.ACCOUNTS_RECEIVABLE.value]
        assert ar_account.code == "1200"
        assert ar_account.name == "Accounts Receivable"
        assert ar_account.account_type == AccountType.ASSET
        assert ar_account.is_system is True

        revenue_account = resolved[AccountMappingKey.SALES_REVENUE.value]
        assert revenue_account.code == "4000"
        assert revenue_account.account_type == AccountType.REVENUE

        tax_account = resolved[AccountMappingKey.SALES_TAX_PAYABLE.value]
        assert tax_account.code == "2200"
        assert tax_account.account_type == AccountType.LIABILITY

        inv_account = resolved[AccountMappingKey.INVENTORY_ASSET.value]
        assert inv_account.code == "1300"
        assert inv_account.account_type == AccountType.ASSET

        var_account = resolved[AccountMappingKey.STOCK_VARIANCE_EXPENSE.value]
        assert var_account.code == "5050"
        assert var_account.account_type == AccountType.EXPENSE

        # Verify idempotency: calling get_default_account again returns the same record
        ar_again = await get_default_account(db_session, AccountMappingKey.ACCOUNTS_RECEIVABLE)
        assert ar_again.id == ar_account.id

    async def test_invoice_posted_consumer_and_idempotency(
        self,
        db_session: AsyncSession,
        seed_tenant_and_users,
    ):
        """Verify sales.invoice_posted translates to DR AR, CR Revenue, CR Tax Payable and is idempotent."""
        invoice_id = uuid4()
        event = DomainEvent(
            event_type="sales.invoice_posted",
            tenant_id="test-tenant",
            payload={
                "id": str(invoice_id),
                "invoice_number": "INV-2026-8001",
                "grand_total": "1140.0000",
                "subtotal": "1000.0000",
                "tax_total": "140.0000",
            },
        )

        entry = await handle_invoice_posted(event, session=db_session)
        assert entry is not None
        assert entry.status == JournalEntryStatus.POSTED
        assert entry.reference == "INV-INV-2026-8001"
        assert entry.reference_id == invoice_id
        assert entry.source_type == "sales.invoice"
        assert entry.source_id == invoice_id

        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        assert total_debit == Decimal("1140.0000")
        assert total_credit == Decimal("1140.0000")
        assert total_debit == total_credit

        line_map = {line.account_code: line for line in entry.lines}
        assert "1200" in line_map  # AR
        assert line_map["1200"].debit == Decimal("1140.0000")
        assert line_map["1200"].credit == Decimal("0.0000")

        assert "4000" in line_map  # Sales Revenue
        assert line_map["4000"].credit == Decimal("1000.0000")
        assert line_map["4000"].debit == Decimal("0.0000")

        assert "2200" in line_map  # Sales Tax Payable
        assert line_map["2200"].credit == Decimal("140.0000")
        assert line_map["2200"].debit == Decimal("0.0000")

        # ── Test Idempotency: Re-processing same event must return same entry and not duplicate ──
        entry_retry = await handle_invoice_posted(event, session=db_session)
        assert entry_retry is not None
        assert entry_retry.id == entry.id

        stmt = select(func.count()).select_from(JournalEntry).where(JournalEntry.reference_id == invoice_id)
        count_res = await db_session.execute(stmt)
        assert count_res.scalar_one() == 1

    async def test_invoice_posted_zero_tax(
        self,
        db_session: AsyncSession,
        seed_tenant_and_users,
    ):
        """Verify sales.invoice_posted with zero tax creates only AR and Revenue lines and balances correctly."""
        invoice_id = uuid4()
        event = DomainEvent(
            event_type="sales.invoice_posted",
            tenant_id="test-tenant",
            payload={
                "id": str(invoice_id),
                "invoice_number": "INV-2026-8002",
                "grand_total": "500.0000",
                "subtotal": "500.0000",
                "tax_total": "0.0000",
            },
        )

        entry = await handle_invoice_posted(event, session=db_session)
        assert entry is not None
        assert len(entry.lines) == 2  # Only DR AR and CR Revenue, no 0-amount tax line
        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        assert total_debit == Decimal("500.0000")
        assert total_credit == Decimal("500.0000")

    async def test_credit_note_posted_consumer(
        self,
        db_session: AsyncSession,
        seed_tenant_and_users,
    ):
        """Verify sales.credit_note_posted translates to CR AR, DR Revenue, DR Tax Payable."""
        credit_note_id = uuid4()
        event = DomainEvent(
            event_type="sales.credit_note_posted",
            tenant_id="test-tenant",
            payload={
                "credit_note_id": str(credit_note_id),
                "return_number": "RET-2026-301",
                "grand_total": "228.0000",
                "subtotal": "200.0000",
                "tax_total": "28.0000",
            },
        )

        entry = await handle_credit_note_posted(event, session=db_session)
        assert entry is not None
        assert entry.status == JournalEntryStatus.POSTED
        assert entry.reference == "CN-RET-2026-301"

        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        assert total_debit == Decimal("228.0000")
        assert total_credit == Decimal("228.0000")

        line_map = {line.account_code: line for line in entry.lines}
        assert line_map["1200"].credit == Decimal("228.0000")  # CR AR
        assert line_map["4000"].debit == Decimal("200.0000")   # DR Revenue Reversal
        assert line_map["2200"].debit == Decimal("28.0000")    # DR Tax Reversal

        # Idempotency check
        entry_retry = await handle_credit_note_posted(event, session=db_session)
        assert entry_retry is not None
        assert entry_retry.id == entry.id

    async def test_stock_take_posted_consumer_variance(
        self,
        db_session: AsyncSession,
        seed_tenant_and_users,
    ):
        """Verify inventory.stock_take_posted translates stock gains & losses to balanced GL lines."""
        stock_take_id = uuid4()
        event = DomainEvent(
            event_type="inventory.stock_take_posted",
            tenant_id="test-tenant",
            payload={
                "stock_take_id": str(stock_take_id),
                "reference_id": "ST-2026-500",
                "total_gain_value": "750.2500",
                "total_loss_value": "300.2500",
            },
        )

        entry = await handle_stock_take_posted(event, session=db_session)
        assert entry is not None
        assert entry.status == JournalEntryStatus.POSTED
        assert entry.reference == "ST-2026-500"

        # Gain=750.25 (DR Asset, CR Variance), Loss=300.25 (DR Variance, CR Asset) -> Total DR = 1050.5000
        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        assert total_debit == Decimal("1050.5000")
        assert total_credit == Decimal("1050.5000")

        # Verify idempotency
        entry_retry = await handle_stock_take_posted(event, session=db_session)
        assert entry_retry is not None
        assert entry_retry.id == entry.id

    async def test_stock_take_posted_zero_variance_skips(
        self,
        db_session: AsyncSession,
        seed_tenant_and_users,
    ):
        """Verify inventory.stock_take_posted with zero variance skips journal entry creation."""
        stock_take_id = uuid4()
        event = DomainEvent(
            event_type="inventory.stock_take_posted",
            tenant_id="test-tenant",
            payload={
                "stock_take_id": str(stock_take_id),
                "reference_id": "ST-2026-501",
                "total_gain_value": "0.0000",
                "total_loss_value": "0.0000",
            },
        )

        entry = await handle_stock_take_posted(event, session=db_session)
        assert entry is None
