"""
app.modules.billing.services.seed — Initial Plan Seeding (Phase 8)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models.core import Plan, PlanTier

logger = logging.getLogger(__name__)


async def seed_plans(session: AsyncSession) -> None:
    """
    Seeds the predefined billing plans (Entry, Professional, Enterprise).
    """
    plans: list[dict[str, Any]] = [
        {
            "code": "ENTRY_MONTHLY",
            "tier": PlanTier.ENTRY,
            "price_monthly": Decimal("499.00"),
            "entitlements": {
                "max_branches": 1,
                "multi_branch": False,
                "approval_workflows": False,
                "api_access": False,
            }
        },
        {
            "code": "PRO_MONTHLY",
            "tier": PlanTier.PROFESSIONAL,
            "price_monthly": Decimal("999.00"),
            "entitlements": {
                "max_branches": 3,
                "multi_branch": True,
                "approval_workflows": False,
                "api_access": True,
            }
        },
        {
            "code": "ENTERPRISE_MONTHLY",
            "tier": PlanTier.ENTERPRISE,
            "price_monthly": Decimal("2499.00"),
            "entitlements": {
                "max_branches": 999,
                "multi_branch": True,
                "approval_workflows": True,
                "api_access": True,
                "dedicated_account_manager": True,
            }
        }
    ]

    for p in plans:
        stmt = select(Plan).where(Plan.code == p["code"])
        exists = (await session.execute(stmt)).scalar_one_or_none()
        
        if not exists:
            logger.info(f"Seeding plan: {p['code']}")
            plan = Plan(
                code=p["code"],
                tier=p["tier"],
                price_monthly=p["price_monthly"],
                entitlements=p["entitlements"]
            )
            session.add(plan)
            
    await session.commit()
