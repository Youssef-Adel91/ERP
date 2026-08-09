"""
app/modules/purchasing/router.py — Purchasing Module Router Registry
"""
from fastapi import APIRouter

from app.modules.purchasing.api.allocation import router as allocation_router
from app.modules.purchasing.api.bills import router as bills_router
from app.modules.purchasing.api.orders import router as orders_router
from app.modules.purchasing.api.payments import router as payments_router
from app.modules.purchasing.api.receiving import router as receiving_router

router = APIRouter()
router.include_router(bills_router)
router.include_router(orders_router)
router.include_router(receiving_router)
router.include_router(payments_router)
router.include_router(allocation_router)

__all__ = [
    "router",
    "bills_router",
    "orders_router",
    "receiving_router",
    "payments_router",
    "allocation_router",
]
