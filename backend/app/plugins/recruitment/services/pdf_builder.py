"""
app/plugins/recruitment/services/pdf_builder.py — Offer Letter PDF (A4)

Renders a printable A4 job offer letter for a candidate using reportlab —
same rendering approach as app.plugins.travel.services.pdf_builder (which
itself follows app.modules.sales.services.pdf_builder).

DECOUPLING CONTRACT:
  ✅ Pure function — no DB session, no cross-module querying
  ✅ Caller (the API endpoint) resolves all IDs to names before calling this
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

import io
from datetime import date, datetime, timezone
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_offer_letter_pdf(
    *,
    candidate_name: str,
    profession: str,
    sponsor_name: str,
    target_country: str,
    salary: Decimal | None,
    currency: str = "USD",
    start_date: str | None = None,
    order_reference: str | None = None,
    agency_name: str = "Nexus ERP — Recruitment & Labor Export",
    issue_date: date | None = None,
) -> bytes:
    """Generates a job offer letter PDF and returns raw bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    def line(text: str, size: int = 10, gap: int = 8, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(margin, y, text)
        y -= (size + gap)

    def paragraph(text: str, size: int = 10, gap: int = 8, max_chars: int = 95) -> None:
        nonlocal y
        words = text.split(" ")
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if len(trial) > max_chars:
                line(current, size=size, gap=4)
                current = word
            else:
                current = trial
        if current:
            line(current, size=size, gap=gap)

    def hr() -> None:
        nonlocal y
        c.setLineWidth(0.5)
        c.line(margin, y, width - margin, y)
        y -= 10

    # ── Header ───────────────────────────────────────────────────────────────
    line(agency_name, size=9, gap=2)
    line("Job Offer Letter / خطاب عرض عمل", size=16, bold=True, gap=6)
    hr()

    _issue_date = issue_date or datetime.now(timezone.utc).date()
    line(f"Date / التاريخ: {_issue_date.isoformat()}", size=10)
    if order_reference:
        line(f"Reference / المرجع: {order_reference}", size=10)
    y -= 4

    line(f"Dear {candidate_name} / عزيزي/عزيزتي {candidate_name},", size=11, bold=True, gap=10)

    salary_str = f"{salary:,.2f} {currency}" if salary is not None else "—"
    body = (
        f"We are pleased to offer you the position of {profession} with our "
        f"sponsoring employer, {sponsor_name}, based in {target_country}. "
        f"This letter confirms the key terms of your offer."
    )
    paragraph(body, size=10, gap=10)

    hr()
    line("Terms / الشروط", size=12, bold=True, gap=6)
    line(f"Position / الوظيفة:            {profession}", size=10)
    line(f"Employer / صاحب العمل:         {sponsor_name}", size=10)
    line(f"Country / الدولة:              {target_country}", size=10)
    line(f"Monthly Salary / الراتب الشهري: {salary_str}", size=10)
    line(f"Start Date / تاريخ البدء:      {start_date or 'To be confirmed / سيتم التأكيد لاحقًا'}", size=10)
    y -= 6
    hr()

    paragraph(
        "This offer is subject to successful completion of medical clearance, "
        "visa/work permit processing, and any other requirements of the "
        "destination country's labor regulations. Final terms will be "
        "confirmed in your signed employment contract.",
        size=9, gap=10,
    )
    paragraph(
        "هذا العرض مشروط باجتياز الفحص الطبي، وإجراءات التأشيرة/تصريح العمل، "
        "وأي متطلبات أخرى وفقًا لقوانين العمل في الدولة المستقبلة. سيتم تأكيد "
        "الشروط النهائية في عقد العمل الموقّع.",
        size=9, gap=14,
    )

    hr()
    line("Signature / التوقيع: ______________________", size=10, gap=6)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line(f"Generated: {generated_at}", size=8, gap=2)
    line("This document is computer-generated.", size=8)

    c.showPage()
    c.save()
    return buf.getvalue()
