"""
app/modules/sales/services/pdf_builder.py — Sales Invoice PDF (A4)

Renders a printable A4 PDF for a SalesInvoice using reportlab (already a
project dependency — see app.modules.cases.services.pdf_builder for the
established rendering conventions this follows: a plain canvas-based
layout with line()/hr() helpers, no template engine, no external assets).

Kept in the `sales` module rather than reused/shared, because the fields
read here (contact name, invoice_number, dates, totals, resolved item
names) are specific to app.modules.sales.models.invoice.SalesInvoice.
app.modules.eta.services.pdf's generate_local_invoice_pdf is purpose-built
for ETA e-invoice/e-receipt submissions (different layout, embeds a
mandatory QR code tied to the ETA UUID) — not reused here, so a plain
"download my invoice" feature doesn't get coupled to the e-invoicing
subsystem's requirements.

Deliberately takes plain data in (no DB session, no cross-module querying)
— same contract as app.modules.cases.services.pdf_builder — so the caller
(the API endpoint) is responsible for resolving contact_id -> name and
item_id -> name before calling this.
"""
from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_sales_invoice_pdf(
    *,
    invoice_number: str,
    status: str,
    issue_date: str,
    due_date: str,
    currency: str,
    contact_name: str,
    subtotal: Decimal,
    tax_total: Decimal,
    grand_total: Decimal,
    lines: list[dict[str, Any]],
) -> bytes:
    """
    `lines` items: {"item_name": str, "qty": Decimal, "unit_price": Decimal,
    "line_total": Decimal}.
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

    # ── Header ──────────────────────────────────────────────────────────
    line("Sales Invoice / فاتورة مبيعات", size=16, bold=True, gap=4)
    line(f"Invoice No: {invoice_number}    Status: {status}", size=11, gap=10)
    hr()

    line(f"Bill To: {contact_name}", size=11, bold=True)
    line(f"Issue Date: {issue_date}    Due Date: {due_date}    Currency: {currency}")
    y -= 4
    hr()

    # ── Line items ──────────────────────────────────────────────────────
    line("Items", size=12, bold=True)
    if not lines:
        line("No line items.", size=9)
    else:
        line(f"{'Item':<32}{'Qty':>8}{'Unit Price':>16}{'Total':>16}", size=9, bold=True)
        for item in lines:
            name = str(item.get("item_name") or "-")[:32]
            qty = item.get("qty", 0)
            unit_price = item.get("unit_price", 0)
            line_total = item.get("line_total", 0)
            line(f"{name:<32}{str(qty):>8}{str(unit_price):>16}{str(line_total):>16}", size=9, gap=4)
            if y < margin + 80:
                c.showPage()
                y = height - margin
    y -= 4
    hr()

    # ── Totals ──────────────────────────────────────────────────────────
    line(f"Subtotal: {subtotal} {currency}")
    line(f"Tax: {tax_total} {currency}")
    line(f"Grand Total: {grand_total} {currency}", bold=True, size=12)

    c.showPage()
    c.save()
    return buf.getvalue()
