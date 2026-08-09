"""
app/modules/cases/api/alerts.py — Expiration Alerts + Travel Itinerary PDF (Core)

Mounted BEFORE the generic `/cases/{id}` router in app.modules.cases.router
so the literal path `/cases/alerts/expirations` isn't swallowed by the
`/cases/{id}` route (FastAPI/Starlette match routes in registration order).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.cases.models.core import Case, CaseType
from app.modules.cases.services.alerts import (
    DEFAULT_THRESHOLD_DAYS,
    ExpirationAlert,
    find_expiring_dates,
    scan_and_publish_expiration_alerts,
)
from app.modules.cases.services.pdf_builder import build_travel_itinerary_pdf
from app.modules.system.dependencies import CurrentUser, require_roles

router = APIRouter(prefix="/cases/alerts", tags=["Case Engine — Alerts"])
itinerary_router = APIRouter(prefix="/cases", tags=["Case Engine — Itinerary PDF"])


@router.get("/expirations", response_model=list[ExpirationAlert])
async def list_expiration_alerts(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
    threshold_days: int = Query(default=DEFAULT_THRESHOLD_DAYS, ge=1, le=365),
):
    """
    Read-only, computed live from Case.data + CaseContact.meta — no
    persisted alert table exists (or is needed) since this is cheap to
    scan on demand for a dashboard widget. See services/alerts.py's module
    docstring for why this doesn't write to a Notification table.
    """
    return await find_expiring_dates(session, threshold_days=threshold_days)


@router.post(
    "/scan",
    response_model=list[ExpirationAlert],
    dependencies=[require_roles("OWNER", "ADMIN")],
)
async def run_expiration_scan(
    request: Request,
    session: AsyncSession = Depends(get_tenant_db),
    threshold_days: int = Query(default=DEFAULT_THRESHOLD_DAYS, ge=1, le=365),
):
    """
    Admin-triggered batch run: same scan as GET /expirations, but also
    publishes one `case.expiration_alert` DomainEvent per hit — the
    "generate an internal system notification" hook. Follows the same
    admin-triggered "batch job" convention already used for
    POST /sales/recurring-invoices/run and POST /sales/reminders/run.
    """
    tenant_id: str = request.state.tenant_id
    alerts = await scan_and_publish_expiration_alerts(session, tenant_id, threshold_days=threshold_days)
    await session.commit()
    return alerts


@itinerary_router.get("/{case_id}/itinerary.pdf")
async def get_travel_itinerary_pdf(
    case_id: UUID,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_tenant_db),
):
    case = await session.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    case_type = await session.get(CaseType, case.case_type_id)
    if not case_type or case_type.plugin_key != "travel":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Itinerary PDFs are only available for travel_booking cases.",
        )

    pdf_bytes = build_travel_itinerary_pdf(case.title, case.data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="itinerary-{case_id}.pdf"'},
    )
