"""
app/modules/portal/router.py — Portal Module Router Registry
"""
from fastapi import APIRouter
from app.modules.portal.api.auth import router as auth_router
from app.modules.portal.api.statements import router as statements_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(statements_router)
