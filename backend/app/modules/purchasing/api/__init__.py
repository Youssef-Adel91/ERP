"""
app.modules.purchasing.api — Purchasing FastAPI Routers
"""
from app.modules.purchasing.api.bills import router as bills_router

__all__ = ["bills_router"]
