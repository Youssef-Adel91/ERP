"""
app/plugins/travel/services/pdf_builder.py — Travel Booking Confirmation PDF (A4)

Renders a printable A4 booking confirmation for a travel booking Case using
reportlab (already a project dependency — same rendering approach as
app.modules.sales.services.pdf_builder).

Layout:
  - Header: agency name + "Booking Confirmation / تأكيد الحجز"
  - Booking reference, customer name, destination, travel/return dates
  - Stage / status
  - Services table: service type, supplier, description, sell price
  - Financial summary: total sell price, total buy price (agency cost), margin
  - Passenger list (if any)
  - Footer: generated date

DECOUPLING CONTRACT:
  ✅ Pure function — no DB session, no cross-module querying
  ✅ Caller (the API endpoint) resolves all IDs to names before calling this
  ❌ Never imports from app.modules.accounting
"""
from __future__ import annotations

import io
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_booking_confirmation_pdf(
    *,
    booking_ref: str,
    customer_name: str,
    destination: str,
    origin: str | None,
    travel_date: str | None,
    return_date: str | None,
    current_stage: str,
    currency: str,
    services: list[dict[str, Any]],
    total_sell_price: Decimal,
    total_buy_price: Decimal,
    passengers: list[dict[str, Any]] | None = None,
    agency_name: str = "Nexus ERP — Travel Agency",
) -> bytes:
    """
    Generates a PDF booking confirmation and returns raw bytes.

    `services` items expected shape (all fields optional):
      {"service_type": str, "supplier_name": str, "description": str,
       "sell_price": float, "currency": str, "quantity": int}

    `passengers` items expected shape (all fields optional):
      {"full_name": str, "passport_number": str, "nationality": str, "passenger_type": str}
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    # ── helpers ──────────────────────────────────────────────────────────────

    def line(text: str, size: int = 10, gap: int = 6, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(margin, y, text)
        y -= (size + gap)

    def hr() -> None:
        nonlocal y
        c.setLineWidth(0.5)
        c.line(margin, y, width - margin, y)
        y -= 8

    def maybe_new_page(needed: int = 40) -> None:
        nonlocal y
        if y < margin + needed:
            c.showPage()
            y = height - margin

    # ── Header ───────────────────────────────────────────────────────────────
    line(agency_name, size=9, gap=2)
    line("Booking Confirmation / تأكيد الحجز", size=15, bold=True, gap=4)
    hr()

    # ── Booking details ───────────────────────────────────────────────────────
    line(f"Booking Ref / رقم الحجز:  {booking_ref}", size=11, bold=True)
    line(f"Customer / العميل:         {customer_name}", size=10)
    line(f"Destination / الوجهة:      {destination}" + (f"  ←  {origin}" if origin else ""), size=10)
    line(f"Travel Date / تاريخ السفر: {travel_date or '—'}", size=10)
    line(f"Return Date / تاريخ العودة: {return_date or '—'}", size=10)
    line(f"Status / الحالة:           {current_stage}", size=10)
    y -= 4
    hr()

    # ── Services ─────────────────────────────────────────────────────────────
    line("Services / الخدمات المشمولة", size=12, bold=True, gap=4)
    if not services:
        line("No services listed.", size=9)
    else:
        header = f"{'Type':<16}{'Supplier':<22}{'Description':<30}{'Qty':>4}{'Price':>14}"
        line(header, size=8, bold=True, gap=3)
        c.setLineWidth(0.3)
        c.line(margin, y + 4, width - margin, y + 4)
        y -= 4

        for svc in services:
            maybe_new_page(20)
            svc_type = str(svc.get("service_type") or "").replace("_", " ").title()[:16]
            supplier = str(svc.get("supplier_name") or "")[:22]
            desc = str(svc.get("description") or "")[:30]
            qty = int(svc.get("quantity") or 1)
            price = Decimal(str(svc.get("sell_price") or 0))
            cur = str(svc.get("currency") or currency)
            price_str = f"{price * qty:,.2f} {cur}"[:14]
            row = f"{svc_type:<16}{supplier:<22}{desc:<30}{qty:>4}{price_str:>14}"
            line(row, size=8, gap=3)

    y -= 4
    hr()

    # ── Financial summary ─────────────────────────────────────────────────────
    line("Financial Summary / الملخص المالي", size=12, bold=True, gap=4)
    total_margin = total_sell_price - total_buy_price
    margin_pct = (
        ((total_margin / total_sell_price) * 100).quantize(Decimal("0.01"))
        if total_sell_price > 0 else Decimal("0")
    )
    line(f"Total Sell Price / إجمالي سعر البيع:   {total_sell_price:,.2f} {currency}", size=10, bold=True)
    line(f"Agency Cost / تكلفة الوكالة:           {total_buy_price:,.2f} {currency}", size=10)
    line(f"Margin / هامش الربح:                   {total_margin:,.2f} {currency}  ({margin_pct}%)", size=10)
    y -= 4
    hr()

    # ── Passenger list ────────────────────────────────────────────────────────
    if passengers:
        maybe_new_page(40)
        line("Passengers / قائمة الركاب", size=12, bold=True, gap=4)
        header = f"{'Name':<36}{'Passport':<18}{'Nationality':<18}{'Type':<8}"
        line(header, size=8, bold=True, gap=3)
        c.setLineWidth(0.3)
        c.line(margin, y + 4, width - margin, y + 4)
        y -= 4

        for pax in passengers:
            maybe_new_page(18)
            name = str(pax.get("full_name") or "")[:36]
            passport = str(pax.get("passport_number") or "—")[:18]
            nationality = str(pax.get("nationality") or "—")[:18]
            pax_type = str(pax.get("passenger_type") or "adult")[:8]
            row = f"{name:<36}{passport:<18}{nationality:<18}{pax_type:<8}"
            line(row, size=8, gap=3)

        hr()

    # ── Footer ────────────────────────────────────────────────────────────────
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line(f"Generated: {generated_at}", size=8, gap=2)
    line("This document is computer-generated and does not require a signature.", size=8)

    c.showPage()
    c.save()
    return buf.getvalue()
