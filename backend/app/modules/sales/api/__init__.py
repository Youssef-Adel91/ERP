"""
app.modules.sales.api — Sales FastAPI Routers
"""
from app.modules.sales.api.invoices import router as invoices_router

__all__ = ["invoices_router"]
