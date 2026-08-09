"""
app/plugins/hospitality/api/bootstrap.py — Plugin activation endpoint
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.plugins.hospitality.bootstrap import bootstrap_hospitality_case_type

router = APIRouter(prefix="/hospitality", tags=["Hospitality – Setup"])


@router.post("/bootstrap")
async def activate_plugin(session: AsyncSession = Depends(get_tenant_db)):
    """Idempotent: injects the 'room_reservation' CaseType into the core engine."""
    ct = await bootstrap_hospitality_case_type(session)
    await session.commit()
    return {
        "message": "Hospitality plugin activated.",
        "case_type_id": str(ct.id),
        "uses_resource": True,
    }
