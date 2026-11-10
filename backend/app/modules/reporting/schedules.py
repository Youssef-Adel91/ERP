"""
app/modules/reporting/schedules.py — Scheduled e-mailed reports

A tenant owner/admin picks any report from the catalogue, a recipient list,
a frequency and a rolling period; a cron (see app/scripts/run_report_schedules.py
or POST /ai/schedules/run-due) calls `run_due_schedules`, which runs the
report, renders it as xlsx/csv and e-mails it via the existing SMTP sender.

Design notes
  * Enum-free table, created lazily (CREATE TABLE IF NOT EXISTS semantics via
    checkfirst) so EXISTING tenants get it without an alembic revision — the
    migration chain on this repo has a history of enum-type collisions.
  * Rolling periods are resolved at run time ("yesterday", "last_7_days", ...)
    so a weekly schedule never ships stale static dates.
  * Never raises into the cron loop: each schedule records last_status.
  * If SMTP isn't configured the schedule is NOT advanced (status "smtp_not_configured")
    so nothing is silently lost once SMTP is set up.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import JSON, Column, Date, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

from app.core.db.base import TenantBase
from app.core.notifications import email as email_sender

logger = logging.getLogger(__name__)

FREQUENCIES = ("daily", "weekly", "monthly")
PERIODS = ("none", "yesterday", "today", "last_7_days", "last_30_days", "month_to_date", "last_month")
MAX_RECIPIENTS = 5


class ReportSchedule(TenantBase, table=True):
    __tablename__ = "report_schedules"
    __table_args__ = ({"schema": "tenant"},)

    name: str = Field(max_length=200)
    report_name: str = Field(sa_column=Column(String(100), nullable=False))
    params: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False, default=dict))
    period: str = Field(default="none", sa_column=Column(String(30), nullable=False, default="none"))
    frequency: str = Field(default="weekly", sa_column=Column(String(20), nullable=False, default="weekly"))
    file_format: str = Field(default="xlsx", sa_column=Column(String(10), nullable=False, default="xlsx"))
    recipients: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False, default=list))
    is_active: bool = Field(default=True)
    next_run_on: date = Field(sa_column=Column(Date, nullable=False))
    last_run_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_status: str | None = Field(default=None, sa_column=Column(String(200)))


async def ensure_table(db: AsyncSession) -> None:
    """Create report_schedules in the current tenant schema if missing (idempotent)."""
    await db.run_sync(lambda s: ReportSchedule.__table__.create(s.connection(), checkfirst=True))


def _advance(frequency: str, frm: date) -> date:
    if frequency == "daily":
        return frm + timedelta(days=1)
    if frequency == "weekly":
        return frm + timedelta(days=7)
    y, m = (frm.year + (frm.month // 12), frm.month % 12 + 1)
    return date(y, m, min(frm.day, 28))


def resolve_period(period: str, today: date) -> dict[str, str]:
    if period == "yesterday":
        d = today - timedelta(days=1)
        return {"date_from": d.isoformat(), "date_to": d.isoformat()}
    if period == "today":
        return {"date_from": today.isoformat(), "date_to": today.isoformat()}
    if period == "last_7_days":
        return {"date_from": (today - timedelta(days=6)).isoformat(), "date_to": today.isoformat()}
    if period == "last_30_days":
        return {"date_from": (today - timedelta(days=29)).isoformat(), "date_to": today.isoformat()}
    if period == "month_to_date":
        return {"date_from": today.replace(day=1).isoformat(), "date_to": today.isoformat()}
    if period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return {"date_from": end.replace(day=1).isoformat(), "date_to": end.isoformat()}
    return {}


def validate_spec(report_name: str, frequency: str, period: str, file_format: str, recipients: list[str]) -> str | None:
    """Returns an error message, or None when valid."""
    from app.modules.reporting.service import REPORT_REGISTRY

    if report_name not in REPORT_REGISTRY:
        return "تقرير غير معروف."
    if frequency not in FREQUENCIES:
        return "التكرار لازم يكون daily أو weekly أو monthly."
    if period not in PERIODS:
        return "الفترة غير مدعومة."
    if file_format not in ("xlsx", "csv"):
        return "الصيغة لازم تكون xlsx أو csv."
    if not recipients or len(recipients) > MAX_RECIPIENTS:
        return f"لازم من 1 إلى {MAX_RECIPIENTS} عناوين بريد."
    if any("@" not in r or " " in r or len(r) > 320 for r in recipients):
        return "عنوان بريد غير صحيح."
    return None


async def run_schedule(db: AsyncSession, sch: ReportSchedule, tenant_id: str | None, today: date | None = None) -> str:
    """Run one schedule now. Returns the status string (also stored on the row)."""
    from app.modules.ai.service import run_report
    from app.modules.reporting.catalog import REPORT_META
    from app.modules.reporting.tabular import normalize, to_csv, to_xlsx

    today = today or date.today()
    if not email_sender.is_configured():
        sch.last_status = "smtp_not_configured"
        return sch.last_status
    try:
        params = {**(sch.params or {}), **resolve_period(sch.period, today)}
        result = await run_report(db, sch.report_name, params, tenant_id)
        table = normalize(sch.report_name, result, REPORT_META.get(sch.report_name, {}).get("title"))
        if sch.file_format == "csv":
            data, mime, ext = to_csv(table), ("text", "csv"), "csv"
        else:
            data, mime, ext = to_xlsx(table), ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"), "xlsx"
        filename = f"{sch.report_name}-{today.isoformat()}.{ext}"
        summary_lines = "\n".join(f"- {k}: {v}" for k, v in list((table.get("summary") or {}).items())[:8])
        body = f"{table['title']}\n\n{summary_lines}\n\nالتقرير كامل في الملف المرفق ({filename}).\n— Trust Core"
        sent = 0
        for to in (sch.recipients or [])[:MAX_RECIPIENTS]:
            ok = await email_sender.send_email(
                to_email=to,
                subject=f"{sch.name} — {today.isoformat()}",
                body_text=body,
                attachments=[(filename, data if isinstance(data, bytes) else data.encode("utf-8"), mime[0], mime[1])],
            )
            sent += 1 if ok else 0
        sch.last_status = f"sent:{sent}/{len(sch.recipients or [])}" if sent else "send_failed"
        if sent:
            sch.next_run_on = _advance(sch.frequency, max(sch.next_run_on, today))
    except Exception as exc:  # one broken schedule must not stop the others
        logger.exception("report schedule %s failed", sch.id)
        sch.last_status = f"error:{type(exc).__name__}"[:200]
    sch.last_run_at = datetime.now(UTC)
    return sch.last_status or ""


async def run_due_schedules(db: AsyncSession, tenant_id: str | None, today: date | None = None) -> list[dict[str, Any]]:
    """Run every active schedule whose next_run_on <= today. Caller commits."""
    await ensure_table(db)
    today = today or date.today()
    due = (
        await db.execute(select(ReportSchedule).where(ReportSchedule.is_active.is_(True), ReportSchedule.deleted_at.is_(None), ReportSchedule.next_run_on <= today))
    ).scalars().all()
    out = []
    for sch in due:
        status = await run_schedule(db, sch, tenant_id, today)
        out.append({"id": str(sch.id), "name": sch.name, "status": status})
    return out


def serialize(s: ReportSchedule) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "name": s.name,
        "report_name": s.report_name,
        "params": s.params or {},
        "period": s.period,
        "frequency": s.frequency,
        "file_format": s.file_format,
        "recipients": s.recipients or [],
        "is_active": s.is_active,
        "next_run_on": s.next_run_on.isoformat(),
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_status": s.last_status,
    }


def parse_id(v: str) -> UUID | None:
    try:
        return UUID(v)
    except ValueError:
        return None
