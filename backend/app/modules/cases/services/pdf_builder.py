"""
app.modules.cases.services.pdf_builder — Travel Itinerary PDF (Core service)

Builds a client-facing itinerary PDF for a "travel_booking" Case, using
reportlab (already a project dependency — see app.modules.eta.services.pdf
for the existing usage/rendering conventions this follows).

Architecture note (per explicit instruction): Case.data is dynamic JSON —
there is no fixed schema at the database level. This module does NOT
assume a plugin_key/case_type_code before extracting; the caller (the API
endpoint) is responsible for confirming the Case is a travel booking.
Extraction itself uses `.get(...)` with defaults throughout so a booking
that hasn't reached the "quotation" stage yet (no buy/sell price set) or
has an empty passenger_manifest still renders a valid, if sparser, PDF
instead of raising — this mirrors the "robust extraction" instruction:
read only the keys we know the travel schema (app.plugins.travel.bootstrap)
defines, and degrade gracefully if any are absent.
"""
from __future__ import annotations

import io
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _get(data: dict[str, Any], key: str, default: Any = "") -> Any:
    value = data.get(key, default)
    return value if value is not None else default


def build_travel_itinerary_pdf(case_title: str | None, case_data: dict[str, Any]) -> bytes:
    """
    Renders an A4 itinerary PDF from a travel_booking Case's cumulative
    `data` payload (fields accumulate across stages — see
    app.modules.cases.services.engine.transition_case's shallow-merge
    data_patch behavior — so by any stage after "inquiry" the destination/
    passenger_manifest/services keys set at "inquiry" are still present
    alongside later ones like buy_price/sell_price from "quotation").

    Known keys read (all optional, per app.plugins.travel.bootstrap's
    TRAVEL_BOOKING_STAGES schema):
      destination, origin, travel_date_requested, return_date_requested,
      trip_type, passenger_manifest[], services[], currency,
      quotation_reference, buy_price, sell_price, confirmation_reference,
      ticket_numbers[].
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    def line(text: str, size: int = 10, gap: int = 6, bold: bool = False) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(margin, y, text)
        y -= (size + gap)

    def hr() -> None:
        nonlocal y
        c.setLineWidth(0.5)
        c.line(margin, y, width - margin, y)
        y -= 10

    # ── Header ──────────────────────────────────────────────────────────────
    line("Travel Itinerary / برنامج الرحلة", size=16, bold=True, gap=4)
    line(case_title or "Untitled Booking", size=11, gap=10)
    hr()

    # ── Trip summary ────────────────────────────────────────────────────────
    line("Trip Summary", size=12, bold=True)
    line(f"Origin: {_get(case_data, 'origin', '-')}    Destination: {_get(case_data, 'destination', '-')}")
    line(f"Departure: {_get(case_data, 'travel_date_requested', '-')}    Return: {_get(case_data, 'return_date_requested', '-')}")
    line(f"Trip Type: {_get(case_data, 'trip_type', '-')}    Currency: {_get(case_data, 'currency', 'EGP')}")
    if _get(case_data, "confirmation_reference"):
        line(f"Confirmation Ref: {_get(case_data, 'confirmation_reference')}")
    ticket_numbers = _get(case_data, "ticket_numbers", [])
    if ticket_numbers:
        line(f"Ticket Numbers: {', '.join(str(t) for t in ticket_numbers)}")
    y -= 4
    hr()

    # ── Passenger manifest ──────────────────────────────────────────────────
    line("Passengers", size=12, bold=True)
    passengers = _get(case_data, "passenger_manifest", [])
    if not passengers:
        line("No passengers recorded yet.", size=9)
    else:
        for p in passengers:
            if not isinstance(p, dict):
                continue
            name = _get(p, "full_name", "-")
            passport = _get(p, "passport_number", "-")
            nationality = _get(p, "nationality", "-")
            ptype = _get(p, "passenger_type", "adult")
            line(f"• {name}  —  Passport: {passport}  —  {nationality}  ({ptype})", size=9, gap=4)
            if y < margin + 60:
                c.showPage()
                y = height - margin
    y -= 4
    hr()

    # ── Services ────────────────────────────────────────────────────────────
    line("Services", size=12, bold=True)
    services = _get(case_data, "services", [])
    if not services:
        line("No services recorded yet.", size=9)
    else:
        for s in services:
            if not isinstance(s, dict):
                continue
            stype = _get(s, "service_type", "-")
            supplier = _get(s, "supplier_name", "-")
            desc = _get(s, "description", "")
            qty = _get(s, "quantity", 1)
            line(f"• {stype} — {supplier} {('— ' + desc) if desc else ''} (x{qty})", size=9, gap=4)
            if y < margin + 60:
                c.showPage()
                y = height - margin
    y -= 4
    hr()

    # ── Financial summary (only if quotation stage reached) ────────────────
    if _get(case_data, "buy_price") or _get(case_data, "sell_price"):
        line("Financial Summary", size=12, bold=True)
        currency = _get(case_data, "currency", "EGP")
        line(f"Sell Price: {_get(case_data, 'sell_price', '-')} {currency}")
        if _get(case_data, "quotation_reference"):
            line(f"Quotation Ref: {_get(case_data, 'quotation_reference')}")

    c.showPage()
    c.save()
    return buf.getvalue()
