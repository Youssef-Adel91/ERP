"""
app/modules/accounting/services/mappings.py — Default GL Account Mappings

Resolves default Chart of Accounts entries for automated financial event consumers (The GL Bridge).
If a default account is not yet present in the tenant schema, this service scaffolds it automatically.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.models.core import Account, AccountType

logger = logging.getLogger(__name__)


class AccountMappingKey(str, Enum):
    """Core accounting mapping keys required by automated domain event consumers."""

    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    SALES_REVENUE = "SALES_REVENUE"
    SALES_TAX_PAYABLE = "SALES_TAX_PAYABLE"
    INVENTORY_ASSET = "INVENTORY_ASSET"
    STOCK_VARIANCE_EXPENSE = "STOCK_VARIANCE_EXPENSE"
    GRNI_ACCRUAL = "GRNI_ACCRUAL"
    ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"
    INPUT_VAT_RECEIVABLE = "INPUT_VAT_RECEIVABLE"
    LANDED_COST_CLEARING = "LANDED_COST_CLEARING"
    CASH_AND_BANKS = "CASH_AND_BANKS"
    CASH_WITH_CARRIER = "CASH_WITH_CARRIER"
    FX_VARIANCE_EXPENSE = "FX_VARIANCE_EXPENSE"
    SHIPPING_EXPENSE = "SHIPPING_EXPENSE"
    COD_FEE_EXPENSE = "COD_FEE_EXPENSE"
    RETURN_FEE_EXPENSE = "RETURN_FEE_EXPENSE"


# Bug fix (live-reproduced, 20 Sep 2026): these codes used to be disjoint
# from the tenant's actual seeded Chart of Accounts (see DEFAULT_ACCOUNTS in
# app/modules/accounting/models/core.py). SALES_REVENUE pointed at code
# "4000" while the seed's Sales Revenue account is "4010", and
# ACCOUNTS_PAYABLE pointed at "2000" while the seed's Accounts Payable
# account is "2100". Because get_default_account() below looks accounts up
# by code and silently scaffolds a brand-new account when the code isn't
# found, every posted sales invoice or vendor bill created a *second*,
# English-only, duplicate account ("4000 - Sales Revenue" next to the
# already-seeded "4010 - إيرادات المبيعات", and "2000 - Accounts Payable"
# next to "2100 - الموردون") instead of posting into the tenant's real
# chart of accounts — fragmenting every financial report across two ledger
# accounts for the same concept. Fixed by aligning these two codes with the
# seed, and by adding name_ar to every entry (used by get_default_account
# below) so any account this service *does* legitimately need to scaffold
# (e.g. Sales Tax Payable, GRNI Accrual — which have no seed equivalent)
# still gets a proper Arabic name instead of English-only.
DEFAULT_ACCOUNT_CONFIGS: dict[AccountMappingKey, dict[str, Any]] = {
    AccountMappingKey.ACCOUNTS_RECEIVABLE: {
        "code": "1200",
        "name": "Accounts Receivable",
        "name_ar": "العملاء (حسابات مدينة)",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.SALES_REVENUE: {
        "code": "4010",
        "name": "Sales Revenue",
        "name_ar": "إيرادات المبيعات",
        "account_type": AccountType.REVENUE,
    },
    AccountMappingKey.SALES_TAX_PAYABLE: {
        "code": "2200",
        "name": "Sales Tax Payable",
        "name_ar": "ضريبة المبيعات المستحقة",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.INVENTORY_ASSET: {
        "code": "1300",
        "name": "Inventory Asset",
        "name_ar": "المخزون",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.STOCK_VARIANCE_EXPENSE: {
        "code": "5050",
        "name": "Stock Variance Expense",
        "name_ar": "فروقات المخزون",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.GRNI_ACCRUAL: {
        "code": "2110",
        "name": "GRNI Accrual",
        "name_ar": "مستحقات بضاعة مستلمة غير مفوترة",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.ACCOUNTS_PAYABLE: {
        "code": "2100",
        "name": "Accounts Payable",
        "name_ar": "الموردون (حسابات دائنة)",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.INPUT_VAT_RECEIVABLE: {
        "code": "1400",
        "name": "Input VAT Receivable",
        "name_ar": "ضريبة القيمة المضافة القابلة للخصم",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.LANDED_COST_CLEARING: {
        "code": "2120",
        "name": "Landed Cost Clearing",
        "name_ar": "مصاريف الشحن والاستيراد المعلقة",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.CASH_AND_BANKS: {
        "code": "1100",
        "name": "Cash and Banks",
        "name_ar": "النقدية وما يعادلها",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.CASH_WITH_CARRIER: {
        "code": "1150",
        "name": "Cash with Carrier",
        "name_ar": "نقدية لدى شركة الشحن",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.FX_VARIANCE_EXPENSE: {
        "code": "5100",
        "name": "FX Variance Expense",
        "name_ar": "فروقات أسعار الصرف",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.SHIPPING_EXPENSE: {
        "code": "5200",
        "name": "Shipping Expense",
        "name_ar": "مصاريف الشحن",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.COD_FEE_EXPENSE: {
        "code": "5210",
        "name": "COD Fee Expense",
        "name_ar": "مصاريف التحصيل عند الاستلام",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.RETURN_FEE_EXPENSE: {
        "code": "5220",
        "name": "Return Fee Expense",
        "name_ar": "مصاريف المرتجعات",
        "account_type": AccountType.EXPENSE,
    },
}



def _normalize_key(key: str | AccountMappingKey) -> AccountMappingKey:
    if isinstance(key, AccountMappingKey):
        return key
    try:
        return AccountMappingKey(str(key).upper())
    except ValueError as exc:
        raise KeyError(f"Unsupported accounting mapping key: '{key}'") from exc


async def get_default_account(
    session: AsyncSession,
    mapping_key: str | AccountMappingKey,
) -> Account:
    """
    Resolve and return the default Account for a given mapping key.

    If the account does not already exist in the database (by code), it will be
    created, added to the session, and flushed.
    """
    norm_key = _normalize_key(mapping_key)
    config = DEFAULT_ACCOUNT_CONFIGS[norm_key]
    code = config["code"]

    stmt = select(Account).where(Account.code == code)
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()

    if account is None:
        logger.info(
            "Default GL account '%s' (code %s) not found in schema; scaffolding automatically.",
            norm_key.value,
            code,
        )
        account = Account(
            code=code,
            name=config["name"],
            name_ar=config.get("name_ar"),
            account_type=config["account_type"],
            is_active=True,
            is_system=True,
        )
        session.add(account)
        await session.flush()

    return account


async def get_default_account_id(
    session: AsyncSession,
    mapping_key: str | AccountMappingKey,
) -> UUID:
    """Resolve and return the Account UUID for the given mapping key."""
    account = await get_default_account(session, mapping_key)
    return account.id


async def get_default_account_code(
    session: AsyncSession,
    mapping_key: str | AccountMappingKey,
) -> str:
    """Resolve and return the Account code string for the given mapping key."""
    account = await get_default_account(session, mapping_key)
    return account.code


async def resolve_default_accounts(
    session: AsyncSession,
    keys: list[str | AccountMappingKey],
) -> dict[str, Account]:
    """Resolve multiple default accounts in a single call, returning a dictionary mapped by key string."""
    resolved: dict[str, Account] = {}
    for key in keys:
        norm_key = _normalize_key(key)
        resolved[norm_key.value] = await get_default_account(session, norm_key)
    return resolved
