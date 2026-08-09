"""
app/modules/hr/router.py — HR Module Router Registry
"""
from fastapi import APIRouter
from app.modules.hr.api.payslips import router as payslips_router
from app.modules.hr.api.employees import router as employees_router

router = APIRouter()
router.include_router(employees_router)
router.include_router(payslips_router)
