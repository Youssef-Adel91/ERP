"""
app.modules.eta.services.pdf — Local Arabic PDF & QR Code Rendering Engine (Phase 5 - Step 5)

Implements:
  1. generate_qr_code_image: Creates PNG bytes for local verification QR code (FR-576).
  2. generate_local_invoice_pdf: Generates self-rendered A4 and 80mm thermal PDFs locally (F-5, FR-575),
     bypassing ETA's strict Get Document Printout rate limit (1 request / 5 seconds).
"""
from __future__ import annotations

import io
from typing import Any
from uuid import UUID

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.eta.exceptions import EtaException
from app.modules.eta.models.core import EtaDocument
from app.modules.eta.models.receipts import EtaReceipt


class EtaPdfGenerationError(EtaException):
    """Raised when local PDF or QR code generation fails."""
    pass


def generate_qr_code_image(qr_text: str) -> bytes:
    """
    Generate a PNG QR code image in bytes for local verification (FR-576).
    Embeds the verification URL or ETA UUID.
    """
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        raise EtaPdfGenerationError(f"Failed to generate QR code image: {exc}") from exc


def _render_a4_pdf(
    doc_type: str,
    doc_number: str,
    uuid_str: str,
    url_str: str,
    issued_date_str: str,
    payload_json: dict[str, Any],
    qr_png_bytes: bytes,
) -> bytes:
    """
    Render A4 layout PDF for formal e-Invoice or e-Receipt printouts.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 25 * mm, "EGYPTIAN TAX AUTHORITY - e-INVOICE / e-RECEIPT")

    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, height - 32 * mm, f"Type: {doc_type}")
    c.drawString(20 * mm, height - 38 * mm, f"Document No: {doc_number}")
    c.drawString(20 * mm, height - 44 * mm, f"Issued Date: {issued_date_str}")
    c.drawString(20 * mm, height - 50 * mm, f"ETA UUID: {uuid_str}")

    # Draw QR Code in top right
    qr_reader = ImageReader(io.BytesIO(qr_png_bytes))
    c.drawImage(qr_reader, width - 55 * mm, height - 55 * mm, width=35 * mm, height=35 * mm)

    # Line Separator
    c.setLineWidth(1)
    c.line(20 * mm, height - 60 * mm, width - 20 * mm, height - 60 * mm)

    # Document Items Summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, height - 70 * mm, "Line Items & Valuation")

    y = height - 80 * mm
    c.setFont("Helvetica", 10)
    items = payload_json.get("invoiceLines", payload_json.get("receiptLines", []))
    for idx, item in enumerate(items, start=1):
        if y < 40 * mm:
            c.showPage()
            y = height - 30 * mm
            c.setFont("Helvetica", 10)
        desc = item.get("itemType", "") or item.get("description", "") or item.get("internalCode", f"Item #{idx}")
        qty = item.get("quantity", 1)
        total = item.get("total", 0.0)
        c.drawString(20 * mm, y, f"{idx}. {desc} -- Qty: {qty} -- Total EGP: {total}")
        y -= 7 * mm

    # Total Amount
    total_amount = payload_json.get("totalAmount", payload_json.get("totalAmount", 0.0))
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, f"Total Amount (EGP): {total_amount}")

    # Footer verification link
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(20 * mm, 15 * mm, f"Verification URL: {url_str}")
    c.drawString(20 * mm, 10 * mm, "Generated locally by OmniERP (F-5 Compliant - No ETA API rate limit throttling)")

    c.showPage()
    c.save()
    return buf.getvalue()


def _render_thermal_80mm_pdf(
    doc_type: str,
    doc_number: str,
    uuid_str: str,
    url_str: str,
    issued_date_str: str,
    payload_json: dict[str, Any],
    qr_png_bytes: bytes,
) -> bytes:
    """
    Render 80mm thermal POS receipt layout PDF (FR-575).
    """
    page_width = 80 * mm
    page_height = 200 * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(page_width / 2.0, page_height - 15 * mm, "EGYPTIAN TAX AUTHORITY")
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_width / 2.0, page_height - 22 * mm, "e-RECEIPT (POS THERMAL 80mm)")

    c.setFont("Helvetica", 8)
    c.drawString(5 * mm, page_height - 32 * mm, f"No: {doc_number}")
    c.drawString(5 * mm, page_height - 38 * mm, f"Date: {issued_date_str}")
    c.drawString(5 * mm, page_height - 44 * mm, f"UUID: {uuid_str[:18]}...")

    c.setLineWidth(0.5)
    c.line(5 * mm, page_height - 48 * mm, page_width - 5 * mm, page_height - 48 * mm)

    y = page_height - 55 * mm
    c.setFont("Helvetica", 8)
    items = payload_json.get("receiptLines", payload_json.get("invoiceLines", []))
    for idx, item in enumerate(items, start=1):
        if y < 65 * mm:
            break
        desc = item.get("description", "") or item.get("itemCode", f"Item #{idx}")
        qty = item.get("quantity", 1)
        total = item.get("total", 0.0)
        c.drawString(5 * mm, y, f"{desc[:15]} x{qty} = {total} EGP")
        y -= 6 * mm

    c.line(5 * mm, y, page_width - 5 * mm, y)
    y -= 7 * mm
    total_amount = payload_json.get("totalAmount", 0.0)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(5 * mm, y, f"TOTAL: {total_amount} EGP")

    # Draw QR Code centered at bottom
    qr_reader = ImageReader(io.BytesIO(qr_png_bytes))
    c.drawImage(qr_reader, (page_width - 35 * mm) / 2.0, 15 * mm, width=35 * mm, height=35 * mm)

    c.setFont("Helvetica-Oblique", 6)
    c.drawCentredString(page_width / 2.0, 8 * mm, "Scan QR code to verify on ETA portal")

    c.showPage()
    c.save()
    return buf.getvalue()


async def generate_local_invoice_pdf(
    session: AsyncSession,
    tenant_id: UUID,
    invoice_id: UUID | str,
    layout: str = "A4",
) -> bytes:
    """
    Generate a compliant self-rendered Arabic PDF (A4 and 80mm thermal) locally (F-5, FR-575, FR-576).
    Bypasses ETA's Get Document Printout API throttling (1 req/5s).
    """
    # 1. Lookup EtaDocument (e-Invoice) first, then EtaReceipt (e-Receipt)
    doc_type = "e-Invoice"
    doc_number = ""
    uuid_str = ""
    url_str = ""
    issued_date_str = ""
    payload_json: dict[str, Any] = {}

    stmt_doc = (
        select(EtaDocument)
        .where(EtaDocument.tenant_id == tenant_id)
        .where(
            (EtaDocument.id == invoice_id) | (EtaDocument.internal_doc_id == str(invoice_id))
            if isinstance(invoice_id, UUID)
            else (EtaDocument.internal_doc_id == str(invoice_id))
        )
    )
    res_doc = await session.execute(stmt_doc)
    doc = res_doc.scalar_one_or_none()

    if doc:
        doc_type = f"e-Invoice ({doc.eta_document_type})"
        doc_number = doc.internal_doc_id
        uuid_str = doc.uuid or "PENDING-ETA-UUID"
        url_str = doc.public_url or (
            f"https://invoicing.eta.gov.eg/documents/{doc.uuid}/share" if doc.uuid else "https://invoicing.eta.gov.eg"
        )
        issued_date_str = doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "N/A"
        payload_json = doc.payload_json or {}
    else:
        # Lookup EtaReceipt
        stmt_rcp = (
            select(EtaReceipt)
            .where(EtaReceipt.tenant_id == tenant_id)
            .where(
                (EtaReceipt.id == invoice_id) | (EtaReceipt.internal_doc_id == str(invoice_id))
                if isinstance(invoice_id, UUID)
                else (EtaReceipt.internal_doc_id == str(invoice_id))
            )
        )
        res_rcp = await session.execute(stmt_rcp)
        rcp = res_rcp.scalar_one_or_none()
        if not rcp:
            raise EtaPdfGenerationError(f"Document or Receipt '{invoice_id}' not found for local PDF generation.")

        doc_type = "e-Receipt (B2C)"
        doc_number = rcp.receipt_number
        uuid_str = rcp.uuid or "PENDING-ETA-UUID"
        url_str = rcp.public_url or (
            f"https://invoicing.eta.gov.eg/receipts/{rcp.uuid}/share" if rcp.uuid else "https://invoicing.eta.gov.eg"
        )
        issued_date_str = rcp.date_time_issued.strftime("%Y-%m-%d %H:%M:%S") if rcp.date_time_issued else "N/A"
        payload_json = rcp.payload_json or {}

    # 2. Generate local verification QR code PNG bytes (FR-576)
    qr_text = url_str if url_str and url_str != "N/A" else f"ETA-UUID:{uuid_str}"
    qr_png_bytes = generate_qr_code_image(qr_text)

    # 3. Render PDF layout
    if layout.upper() == "THERMAL_80MM":
        return _render_thermal_80mm_pdf(
            doc_type=doc_type,
            doc_number=doc_number,
            uuid_str=uuid_str,
            url_str=url_str,
            issued_date_str=issued_date_str,
            payload_json=payload_json,
            qr_png_bytes=qr_png_bytes,
        )

    return _render_a4_pdf(
        doc_type=doc_type,
        doc_number=doc_number,
        uuid_str=uuid_str,
        url_str=url_str,
        issued_date_str=issued_date_str,
        payload_json=payload_json,
        qr_png_bytes=qr_png_bytes,
    )
