"""
app/modules/cases/router.py — Case Engine Module Router Registry
"""
from fastapi import APIRouter
from app.modules.cases.api.router import router as cases_router
from app.modules.cases.api.router import resources_router
from app.modules.cases.api.case_types import router as case_types_router
from app.modules.cases.api.alerts import router as alerts_router
from app.modules.cases.api.alerts import itinerary_router
from app.modules.cases.api.vendors import router as vendors_router

router = APIRouter()
router.include_router(case_types_router)
# alerts_router (literal "/cases/alerts/...") and itinerary_router
# ("/cases/{id}/itinerary.pdf") must be included BEFORE cases_router
# (which owns the bare "/cases/{id}" path) — Starlette matches routes in
# registration order, so "/cases/alerts/expirations" would otherwise be
# swallowed by "/cases/{id}" with id="alerts". Same reasoning for
# vendors_router ("/cases/vendors/...") — must precede cases_router too.
router.include_router(alerts_router)
router.include_router(itinerary_router)
router.include_router(vendors_router)
router.include_router(cases_router)
router.include_router(resources_router)
