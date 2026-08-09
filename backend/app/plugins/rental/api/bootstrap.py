"""
app/plugins/rental/api/bootstrap.py — Plugin activation endpoint
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.plugins.rental.bootstrap import bootstrap_rental_case_type

router = APIRouter(prefix="/rental", tags=["Rental – Setup"])


@router.post("/bootstrap")
async def activate_plugin(session: AsyncSession = Depends(get_tenant_db)):
    """Idempotent: injects the 'vehicle_rental' CaseType into the core engine."""
    ct = await bootstrap_rental_case_type(session)
    await session.commit()
    return {
        "message": "Vehicle Rental plugin activated.",
        "case_type_id": str(ct.id),
        "uses_resource": True,
    }
