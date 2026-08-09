"""
app.modules.cases.services.alerts — Expiration Alerts Engine (Core, not per-plugin)

Per SRS_Addendum_v1.1 §A.2/§A.7: Travel and Recruitment cases carry
passport/visa/medical-certificate expiry dates buried inside the dynamic
JSON `Case.data` payload (and inside `CaseContact.meta`, since the
"lead_passenger"/"candidate" contact-role schemas also carry
passport_expiry). Because every vertical defines its own stage schema,
there is no fixed set of column names to query — this scans the JSON
structures directly and pattern-matches on key name.

This lives in Core (app.modules.cases), not in the travel/recruitment
plugins, for the same reason the Case Engine itself is Core: the scan
logic is identical regardless of which vertical the dates belong to.

Honest scope note: there is no persisted Notification/inbox model in this
codebase yet (verified — no `Notification` table exists anywhere). Rather
than fabricate one, this module:
  - exposes `find_expiring_dates()` as a pure, synchronous, on-demand scan
    (used directly by GET /cases/alerts/expirations for the dashboard), and
  - publishes a real `case.expiration_alert` DomainEvent per hit via the
    existing EventBus (the same transactional-outbox mechanism every other
    domain event in this codebase uses) so a future notification consumer
    can subscribe without any change here. No consumer subscribes yet —
    this endpoint/event is the producer side, wired honestly rather than
    faked.
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.event_bus import DomainEvent, get_event_bus
from app.modules.cases.models.core import Case, CaseContact, CaseType

# Any JSON key containing "expiry" or "expiration" (case-insensitive) is
# treated as a date-like field to check — matches passport_expiry,
# visa_expiry, medical_expiry (via the "medical" stage's examination info
# does NOT itself carry an expiry key today, so nothing false-positives
# there), license_expiry, etc. without hardcoding a per-vertical field list.
EXPIRY_KEY_RE = re.compile(r"expir", re.IGNORECASE)

DEFAULT_THRESHOLD_DAYS = 60


class ExpirationAlert(BaseModel):
    case_id: UUID
    case_title: str | None
    plugin_key: str
    case_type_code: str
    field_path: str
    expiry_date: date
    days_remaining: int
    severity: str  # "expired" | "critical" (<=30d) | "warning" (<=threshold)
    assigned_to: UUID | None  # Case.created_by — no dedicated assignee field exists yet


def _severity(days_remaining: int) -> str:
    if days_remaining < 0:
        return "expired"
    if days_remaining <= 30:
        return "critical"
    return "warning"


def _walk_for_expiry_dates(node: Any, path: str = "") -> list[tuple[str, str]]:
    """Recursively finds (path, raw_date_string) pairs for any key matching EXPIRY_KEY_RE."""
    hits: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(value, str) and EXPIRY_KEY_RE.search(key):
                hits.append((child_path, value))
            elif isinstance(value, (dict, list)):
                hits.extend(_walk_for_expiry_dates(value, child_path))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits.extend(_walk_for_expiry_dates(item, f"{path}[{i}]"))
    return hits


def _parse_date(raw: str) -> date | None:
    try:
        # JSON Schema "date" format is ISO 8601 (YYYY-MM-DD); "date-time" also
        # starts with that, so a straight fromisoformat on the date part covers both.
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


async def find_expiring_dates(
    session: AsyncSession,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
) -> list[ExpirationAlert]:
    """
    Scans all non-terminal Cases' `data` JSON (and their CaseContact.meta)
    for any *_expiry-style date within `threshold_days` of today (including
    already-expired). Read-only — does not publish events; see
    `scan_and_publish_expiration_alerts` for the write-side counterpart.
    """
    today = datetime.now(UTC).date()

    case_stmt = select(Case, CaseType).join(CaseType, Case.case_type_id == CaseType.id).where(
        Case.status.notin_(["CLOSED", "CANCELLED"])
    )
    rows = (await session.execute(case_stmt)).all()

    alerts: list[ExpirationAlert] = []

    for case, case_type in rows:
        for field_path, raw_date in _walk_for_expiry_dates(case.data):
            parsed = _parse_date(raw_date)
            if not parsed:
                continue
            days_remaining = (parsed - today).days
            if days_remaining > threshold_days:
                continue
            alerts.append(
                ExpirationAlert(
                    case_id=case.id,
                    case_title=case.title,
                    plugin_key=case_type.plugin_key,
                    case_type_code=case_type.code,
                    field_path=field_path,
                    expiry_date=parsed,
                    days_remaining=days_remaining,
                    severity=_severity(days_remaining),
                    assigned_to=case.created_by,
                )
            )

        # Also scan CaseContact.meta (e.g. lead_passenger.passport_expiry,
        # candidate.passport_expiry) — attached per-contact, not in Case.data.
        contacts_stmt = select(CaseContact).where(CaseContact.case_id == case.id)
        contacts = (await session.execute(contacts_stmt)).scalars().all()
        for contact in contacts:
            for field_path, raw_date in _walk_for_expiry_dates(contact.meta):
                parsed = _parse_date(raw_date)
                if not parsed:
                    continue
                days_remaining = (parsed - today).days
                if days_remaining > threshold_days:
                    continue
                alerts.append(
                    ExpirationAlert(
                        case_id=case.id,
                        case_title=case.title,
                        plugin_key=case_type.plugin_key,
                        case_type_code=case_type.code,
                        field_path=f"contacts[{contact.role}].{field_path}",
                        expiry_date=parsed,
                        days_remaining=days_remaining,
                        severity=_severity(days_remaining),
                        assigned_to=case.created_by,
                    )
                )

    alerts.sort(key=lambda a: a.days_remaining)
    return alerts


class ExpirationAlertEvent(DomainEvent):
    event_type: str = "case.expiration_alert"


async def scan_and_publish_expiration_alerts(
    session: AsyncSession,
    tenant_id: str,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
) -> list[ExpirationAlert]:
    """
    Runs the same scan as find_expiring_dates(), and additionally publishes
    one `case.expiration_alert` DomainEvent per hit to the EventBus
    (transactional outbox — caller must commit). Intended to be invoked
    periodically (e.g. via the platform's existing external cron/scheduler
    hitting POST /cases/alerts/scan), following the same admin-triggered
    "batch job" convention already used for sales' recurring-invoice and
    reminder workers in this codebase.
    """
    alerts = await find_expiring_dates(session, threshold_days=threshold_days)
    event_bus = get_event_bus()
    for alert in alerts:
        await event_bus.publish(
            ExpirationAlertEvent(
                tenant_id=tenant_id,
                payload={
                    "case_id": str(alert.case_id),
                    "case_title": alert.case_title,
                    "plugin_key": alert.plugin_key,
                    "field_path": alert.field_path,
                    "expiry_date": alert.expiry_date.isoformat(),
                    "days_remaining": alert.days_remaining,
                    "severity": alert.severity,
                    "assigned_to": str(alert.assigned_to) if alert.assigned_to else None,
                },
            ),
            session=session,
        )
    return alerts
