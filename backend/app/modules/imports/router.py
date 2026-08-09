"""
app/modules/imports/router.py — Imports Module Router Registry
"""
from fastapi import APIRouter
from app.modules.imports.api.dossiers import router as dossiers_router

router = APIRouter()
router.include_router(dossiers_router)
