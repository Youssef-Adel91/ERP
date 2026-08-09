"""
app.modules.finance.router — Aggregated API Router for the Finance Module
"""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.finance.api.settlements import router as settlements_router
from app.modules.finance.api.cheques import router as cheques_router

router = APIRouter()
router.include_router(settlements_router)
router.include_router(cheques_router)

__all__ = ["router", "settlements_router", "cheques_router"]
