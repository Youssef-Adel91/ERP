"""
app.modules.eta.api — ETA Compliance FastAPI Routers (Phase 5)
"""
from app.modules.eta.api.callbacks import router as callbacks_router
from app.modules.eta.api.config import router as config_router
from app.modules.eta.api.submissions import router as submissions_router

__all__ = ["callbacks_router", "config_router", "submissions_router"]
