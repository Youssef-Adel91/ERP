"""
app/modules/ai/router.py — AI Bot (Copilot Level 1: Grounded Retrieval,
Level 4: Agentic Document Drafting)

POST /api/v1/ai/ask is a thin HTTP wrapper around
app.modules.ai.service.answer_question — the actual grounded-retrieval
logic lives there now (extracted 2026-09-11 so
app.plugins.whatsapp.listeners.handle_whatsapp_message_ai_bot can reuse
the exact same live-verified code path instead of a second
implementation). See that module's docstring for the full flow.

Live-verified (2026-09-11): a real posted invoice's numbers came back
through this endpoint byte-for-byte matching the database; a question
with no matching report was correctly declined instead of a fabricated
answer; a bad model name and a missing API key both failed with a clear
Arabic message and a real logged error, no crash.

Read-only by construction — see app.core.ai.adapter's docstring for why
that must stay true even as later Copilot levels get built.

Level 4 additions (2026-09-11): the three endpoints under /drafts let a
user draft an AI-narrated overdue-payment reminder grounded in real
overdue-invoice data, view it, and submit it for approval through the
EXISTING generic Approval Engine (app.modules.approvals) — document_type
"ai_drafted_message". Nothing is sent to a customer by these endpoints;
sending only happens after a real recorded APPROVE decision — see
app.modules.approvals.api.decide and
app.plugins.whatsapp.listeners.handle_ai_draft_approved.
"""
from __future__ import annotations

from uuid import UUID

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.database import get_tenant_db
from app.modules.ai.document_drafting import (
    NoOverdueInvoicesError,
    draft_overdue_payment_reminder,
)
from app.modules.ai.models import AIDraftedMessage
from app.modules.ai.schemas import (
    AskRequest,
    AskResponse,
    DraftOverdueReminderRequest,
    ExportReportRequest,
    RunReportRequest,
    SubmitDraftResponse,
)
from app.modules.ai.service import answer_question, run_report
from app.modules.reporting.catalog import REPORT_META, can_run, suggestions
from app.modules.reporting.service import REPORT_REGISTRY
from app.modules.reporting.tabular import normalize, to_csv, to_xlsx
from app.modules.approvals.services.approval_engine import submit_for_approval
from app.modules.approvals.services.exceptions import IllegalStateTransitionError
from app.modules.system.dependencies import CurrentUser

router = APIRouter(prefix="/ai", tags=["AI Bot"])

AI_DRAFTED_MESSAGE_DOCUMENT_TYPE = "ai_drafted_message"


@router.post("/ask", response_model=AskResponse, summary="Ask the AI Bot about your real numbers")
async def ask(
    body: AskRequest,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AskResponse:
    return await answer_question(
        db, body.question, tenant_id=str(current_user.tenant_id), roles=_roles(request)
    )


@router.post(
    "/drafts/overdue-reminder",
    response_model=AIDraftedMessage,
    status_code=status.HTTP_201_CREATED,
    summary="Draft an AI-narrated overdue payment reminder for one contact",
)
async def create_overdue_reminder_draft(
    body: DraftOverdueReminderRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AIDraftedMessage:
    try:
        draft = await draft_overdue_payment_reminder(db, body.contact_id)
        await db.commit()
        await db.refresh(draft)
        return draft
    except NoOverdueInvoicesError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/drafts/{id}", response_model=AIDraftedMessage, summary="View an AI-drafted message")
async def get_draft(
    id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> AIDraftedMessage:
    draft = await db.get(AIDraftedMessage, id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return draft


@router.post(
    "/drafts/{id}/submit",
    response_model=SubmitDraftResponse,
    summary="Submit an AI-drafted message for human approval",
)
async def submit_draft(
    id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_tenant_db),
) -> SubmitDraftResponse:
    """
    Submits the draft through the SAME generic Approval Engine every other
    approvable document in this codebase uses (submit_for_approval —
    app.modules.approvals.services.approval_engine). approvable_content is
    the draft_text + grounding_data, so a later edit to either is caught by
    the existing content-hash tamper check (FR-1212) at decision time —
    exactly like a purchase order.
    """
    draft = await db.get(AIDraftedMessage, id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")

    approvable_content = {
        "draft_text": draft.draft_text,
        "grounding_data": draft.grounding_data,
    }
    try:
        request = await submit_for_approval(
            session=db,
            document_type=AI_DRAFTED_MESSAGE_DOCUMENT_TYPE,
            document_id=draft.id,
            document=draft,
            requested_by=current_user.id,
            approvable_content=approvable_content,
        )
    except IllegalStateTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(draft)
    await db.refresh(request)
    return SubmitDraftResponse(draft=draft, approval_request_id=request.id)



# ── Phase C: report catalogue, direct run and Excel/CSV export ───────────────


def _roles(request: Request) -> list[str]:
    return list(getattr(request.state, "current_user_roles", []) or [])


def _authorise(name: str, request: Request) -> None:
    if name not in REPORT_REGISTRY:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown report.")
    if not can_run(name, _roles(request)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role may not run this report.")


@router.get("/suggestions", summary="Example questions the assistant understands")
async def get_suggestions(current_user: CurrentUser) -> dict:
    return {"suggestions": suggestions()}


@router.get("/reports/catalog", summary="Reports the caller's role may run")
async def reports_catalog(request: Request, current_user: CurrentUser) -> dict:
    roles = _roles(request)
    items = []
    for name, spec in REPORT_REGISTRY.items():
        if not can_run(name, roles):
            continue
        meta = REPORT_META.get(name, {})
        items.append(
            {
                "name": name,
                "title": meta.get("title", name),
                "category": meta.get("category", "أخرى"),
                "description": spec["description"],
                "params": [
                    {"key": k, "type": v.get("type", "string"), "label": v.get("description", k), "required": k in spec["parameters"].get("required", [])}
                    for k, v in spec["parameters"]["properties"].items()
                ],
            }
        )
    return {"reports": items}


@router.post("/reports/run", summary="Run one report directly and get the standard table")
async def reports_run(
    body: RunReportRequest, request: Request, current_user: CurrentUser, db: AsyncSession = Depends(get_tenant_db)
) -> dict:
    _authorise(body.name, request)
    try:
        result = await run_report(db, body.name, body.params, str(current_user.tenant_id))
    except TypeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Bad report parameters: {exc}") from exc
    return normalize(body.name, result, REPORT_META.get(body.name, {}).get("title"))


@router.post("/reports/export", summary="Download any report as .xlsx or .csv")
async def reports_export(
    body: ExportReportRequest, request: Request, current_user: CurrentUser, db: AsyncSession = Depends(get_tenant_db)
) -> Response:
    _authorise(body.name, request)
    try:
        result = await run_report(db, body.name, body.params, str(current_user.tenant_id))
    except TypeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Bad report parameters: {exc}") from exc
    table = normalize(body.name, result, REPORT_META.get(body.name, {}).get("title"))
    stem = f"{body.name}-{date.today().isoformat()}"
    if body.format == "csv":
        content, media = to_csv(table), "text/csv; charset=utf-8"
    else:
        content, media = to_xlsx(table), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{stem}.{body.format}"', "Access-Control-Expose-Headers": "Content-Disposition"},
    )
