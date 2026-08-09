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


DEFAULT_ACCOUNT_CONFIGS: dict[AccountMappingKey, dict[str, Any]] = {
    AccountMappingKey.ACCOUNTS_RECEIVABLE: {
        "code": "1200",
        "name": "Accounts Receivable",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.SALES_REVENUE: {
        "code": "4000",
        "name": "Sales Revenue",
        "account_type": AccountType.REVENUE,
    },
    AccountMappingKey.SALES_TAX_PAYABLE: {
        "code": "2200",
        "name": "Sales Tax Payable",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.INVENTORY_ASSET: {
        "code": "1300",
        "name": "Inventory Asset",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.STOCK_VARIANCE_EXPENSE: {
        "code": "5050",
        "name": "Stock Variance Expense",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.GRNI_ACCRUAL: {
        "code": "2110",
        "name": "GRNI Accrual",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.ACCOUNTS_PAYABLE: {
        "code": "2000",
        "name": "Accounts Payable",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.INPUT_VAT_RECEIVABLE: {
        "code": "1400",
        "name": "Input VAT Receivable",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.LANDED_COST_CLEARING: {
        "code": "2120",
        "name": "Landed Cost Clearing",
        "account_type": AccountType.LIABILITY,
    },
    AccountMappingKey.CASH_AND_BANKS: {
        "code": "1100",
        "name": "Cash and Banks",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.CASH_WITH_CARRIER: {
        "code": "1150",
        "name": "Cash with Carrier",
        "account_type": AccountType.ASSET,
    },
    AccountMappingKey.FX_VARIANCE_EXPENSE: {
        "code": "5100",
        "name": "FX Variance Expense",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.SHIPPING_EXPENSE: {
        "code": "5200",
        "name": "Shipping Expense",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.COD_FEE_EXPENSE: {
        "code": "5210",
        "name": "COD Fee Expense",
        "account_type": AccountType.EXPENSE,
    },
    AccountMappingKey.RETURN_FEE_EXPENSE: {
        "code": "5220",
        "name": "Return Fee Expense",
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
            account_type=config["account_type"],
            is_active=True,
            is_header=False,
            is_reconciliation=False,
            is_system=True,
            currency="EGP",
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
