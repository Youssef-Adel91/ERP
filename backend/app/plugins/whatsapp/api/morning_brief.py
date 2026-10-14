"""
app/plugins/whatsapp/api/morning_brief.py — Admin-Triggered Morning Brief Run

Every other endpoint in this plugin is tenant-scoped (the caller's own
WhatsApp config, their own tenant). This one is deliberately not: it fans
out over EVERY tenant's WhatsApp config at once (see
app.plugins.whatsapp.services.morning_brief.send_all_morning_briefs), which
is exactly what the daily cron does — this endpoint exists so that fan-out
can be triggered and live-verified on demand instead of waiting for the
clock, same reasoning as app.modules.sales.api.reminders's admin-trigger
endpoint. Gated on User.is_superadmin rather than a per-tenant role for
that reason.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.modules.system.dependencies import CurrentUser
from app.plugins.whatsapp.services.morning_brief import send_all_morning_briefs

router = APIRouter(prefix="/whatsapp/morning-brief", tags=["WhatsApp AI Bot"])


class RunMorningBriefResponse(BaseModel):
    tenants_processed: int
    messages_sent: int
    failures: list[str]


@router.post(
    "/run",
    response_model=RunMorningBriefResponse,
    summary="Superadmin-triggered run: send the AI morning brief to every eligible tenant's authorized WhatsApp numbers",
)
async def run_morning_briefs(current_user: CurrentUser) -> RunMorningBriefResponse:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required.")

    result = await send_all_morning_briefs()
    return RunMorningBriefResponse(**result)
