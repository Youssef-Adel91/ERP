"""
app/modules/inventory/router.py — Inventory Module Router
"""
from fastapi import APIRouter

from app.modules.inventory.api.costing import router as costing_router
from app.modules.inventory.api.items import router as items_router
from app.modules.inventory.api.pricing import router as pricing_router
from app.modules.inventory.api.reservation import router as reservation_router
from app.modules.inventory.api.serial_lifecycle import router as serial_lifecycle_router
from app.modules.inventory.api.stock import router as stock_router
from app.modules.inventory.api.stock_take import router as stock_take_router
from app.modules.inventory.api.transfer import router as transfer_router

router = APIRouter()
router.include_router(stock_router)
router.include_router(items_router)
router.include_router(costing_router)
router.include_router(pricing_router)
router.include_router(reservation_router)
router.include_router(serial_lifecycle_router)
router.include_router(stock_take_router)
router.include_router(transfer_router)

__all__ = [
    "router",
    "stock_router",
    "items_router",
    "costing_router",
    "pricing_router",
    "reservation_router",
    "serial_lifecycle_router",
    "stock_take_router",
    "transfer_router",
]
