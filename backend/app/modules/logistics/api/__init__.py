"""
app.modules.logistics.api — Logistics & Carrier Integration API Routes (Phase 7b)
"""
from app.modules.logistics.api.webhooks import router as webhooks_router
from app.modules.logistics.api.carriers import router as carriers_router
from app.modules.logistics.api.shipments import router as shipments_router

__all__ = ["webhooks_router", "carriers_router", "shipments_router"]
