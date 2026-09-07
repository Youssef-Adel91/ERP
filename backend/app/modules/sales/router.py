"""
app/modules/sales/router.py — Sales Module Router Registry
"""
from fastapi import APIRouter

from app.modules.sales.api.fulfillment import router as fulfillment_router
from app.modules.sales.api.invoices import router as invoices_router
from app.modules.sales.api.orders import router as orders_router
from app.modules.sales.api.payments import router as payments_router
from app.modules.sales.api.recurring import router as recurring_router
from app.modules.sales.api.reminders import router as reminders_router
from app.modules.sales.api.returns import router as returns_router

router = APIRouter()
router.include_router(invoices_router)
router.include_router(orders_router)
router.include_router(fulfillment_router)
router.include_router(returns_router)
router.include_router(payments_router)
router.include_router(recurring_router)
router.include_router(reminders_router)

__all__ = [
    "router",
    "invoices_router",
    "orders_router",
    "fulfillment_router",
    "returns_router",
    "payments_router",
    "recurring_router",
    "reminders_router",
]
