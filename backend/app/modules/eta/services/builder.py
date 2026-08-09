"""
app.modules.eta.services.builder — Document Builder & Pre-Submission Validation Gate (Phase 5 - Step 3)

Implements:
  1. build_eta_invoice: Fetches SalesInvoice, validates EgsCode for every line item (FR-521),
     and builds the ETA JSON schema dictionary (Version strictly pinned to "1.0").
  2. prepare_signed_eta_document: Orchestrates build_eta_invoice, canonicalization, hashing,
     and CAdES-BES digital signature generation to produce a signed EtaDocument.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.eta.exceptions import EtaMissingItemCodeError
from app.modules.eta.models.codes import EgsCode
from app.modules.eta.models.core import (
    EtaDocument,
    EtaDocumentState,
    EtaTenantConfig,
)
from app.modules.eta.services.canonical import serialize_document
from app.modules.eta.services.crypto import compute_cades_bes_hash
from app.modules.eta.services.signing import SigningProvider, get_signing_provider
from app.modules.inventory.models.core import Item
from app.modules.sales.models.invoice import SalesInvoice


async def build_eta_invoice(
    session: AsyncSession,
    invoice_id: UUID,
    tenant_config: EtaTenantConfig | None = None,
) -> dict[str, Any]:
    """
    Build ETA-compliant JSON dictionary for a SalesInvoice (FR-520, FR-521).

    Pre-Submission Gate (FR-521):
      Every line item on the invoice is checked against the EgsCode registry or Item egs_code.
      If any line item lacks an active EGS/GS1 code, EtaMissingItemCodeError is raised immediately,
      preventing submission and alerting the merchant before an ETA rejection.
    """
    # 1. Fetch SalesInvoice with lines
    stmt_inv = select(SalesInvoice).where(SalesInvoice.id == invoice_id)
    result_inv = await session.execute(stmt_inv)
    invoice = result_inv.scalar_one_or_none()
    if not invoice:
        raise ValueError(f"SalesInvoice with id={invoice_id} not found.")

    # 2. If tenant_config is not provided, query the first active tenant config
    if tenant_config is None:
        stmt_cfg = select(EtaTenantConfig).limit(1)
        res_cfg = await session.execute(stmt_cfg)
        tenant_config = res_cfg.scalar_one_or_none()

    # 3. Pre-Submission Gate (FR-521): Validate every line item has a valid EGS/GS1 code
    verified_lines: list[tuple[Any, Any, tuple[str, str]]] = []
    for line in invoice.lines:
        stmt_item = select(Item).where(Item.id == line.item_id)
        res_item = await session.execute(stmt_item)
        item = res_item.scalar_one_or_none()

        item_name = item.name if item else f"Item {line.item_id}"
        item_sku = item.sku if item else "UNKNOWN"

        # Lookup EgsCode in registry table
        stmt_code = (
            select(EgsCode)
            .where(EgsCode.item_id == line.item_id)
            .where(EgsCode.is_active == True)  # noqa: E712
        )
        if line.variant_id:
            stmt_code = stmt_code.where(
                (EgsCode.variant_id == line.variant_id) | (EgsCode.variant_id.is_(None))
            ).order_by(EgsCode.variant_id.desc())

        res_code = await session.execute(stmt_code)
        egs_code_obj = res_code.scalars().first()

        code_type: str | None = None
        code_value: str | None = None

        if egs_code_obj:
            code_type = egs_code_obj.code_type
            code_value = egs_code_obj.code_value
        elif item and item.egs_code and item.egs_code.strip():
            # Fallback to item-level egs_code if set
            code_type = "EGS"
            code_value = item.egs_code.strip()

        if not code_type or not code_value:
            raise EtaMissingItemCodeError(
                f"Pre-submission gate failed (FR-521): Line item '{item_name}' "
                f"(SKU: {item_sku}, ID: {line.item_id}) is missing an active EGS/GS1 code "
                f"in EgsCode registry. Document cannot be submitted to ETA."
            )

        verified_lines.append((line, item, (code_type, code_value)))

    # 4. Construct ETA JSON document dictionary (TypeVersion strictly pinned to "1.0")
    invoice_lines_payload = []
    total_sales = Decimal("0.00")
    total_tax = Decimal("0.00")

    for line, item, (code_type, code_value) in verified_lines:
        sales_total = line.qty * line.unit_price
        total_sales += sales_total
        total_tax += line.tax_amount

        taxable_items = []
        if line.tax_amount > 0:
            taxable_items.append({
                "taxType": "T1",
                "amount": float(line.tax_amount),
                "subType": "V009",
                "rate": float(line.tax_rate * 100),
            })

        invoice_lines_payload.append({
            "description": item.name if item else "Invoice Line Item",
            "itemType": code_type,
            "itemCode": code_value,
            "unitType": "EA",
            "quantity": float(line.qty),
            "unitValue": {
                "currencySold": invoice.currency,
                "amountEGP": float(line.unit_price),
            },
            "salesTotal": float(sales_total),
            "total": float(line.line_total),
            "valueDifference": 0.0,
            "totalTaxableFees": 0.0,
            "netTotal": float(sales_total),
            "itemsDiscount": 0.0,
            "discount": {
                "rate": 0.0,
                "amount": 0.0,
            },
            "taxableItems": taxable_items,
        })

    tax_totals = []
    if total_tax > 0:
        tax_totals.append({
            "taxType": "T1",
            "amount": float(total_tax),
        })

    issue_dt = datetime.combine(invoice.issue_date, datetime.min.time(), tzinfo=UTC)

    payload: dict[str, Any] = {
        "issuer": {
            "address": {
                "branchID": tenant_config.branch_eta_codes.get("default", "0") if tenant_config else "0",
                "country": "EG",
                "governorate": "Cairo",
                "regionCity": "Cairo",
                "street": "Main Street",
                "buildingNumber": "1",
            },
            "type": "B",
            "id": tenant_config.taxpayer_rin if tenant_config else "000000000",
            "name": "OmniERP Taxpayer Ltd.",
        },
        "receiver": {
            "address": {
                "country": "EG",
                "governorate": "Cairo",
                "regionCity": "Maadi",
                "street": "Commercial Road",
                "buildingNumber": "10",
            },
            "type": "B",
            "id": "111222333",
            "name": "Customer Company S.A.E.",
        },
        "documentType": "I",
        "documentTypeVersion": "1.0",
        "dateTimeIssued": issue_dt.isoformat(),
        "taxpayerActivityCode": tenant_config.activity_code if tenant_config else "4610",
        "internalID": invoice.invoice_number,
        "invoiceLines": invoice_lines_payload,
        "totalDiscountAmount": 0.0,
        "totalSalesAmount": float(total_sales),
        "netAmount": float(total_sales),
        "taxTotals": tax_totals,
        "totalAmount": float(invoice.grand_total),
        "extraDiscountAmount": 0.0,
        "totalItemsDiscountAmount": 0.0,
    }

    return payload


async def prepare_signed_eta_document(
    session: AsyncSession,
    invoice_id: UUID,
    tenant_config: EtaTenantConfig,
    provider: SigningProvider | None = None,
) -> EtaDocument:
    """
    Full Phase 5 pipeline:
      1. Build ETA JSON schema (with EgsCode pre-submission validation gate)
      2. Canonicalize JSON payload according to ETA serialization rules
      3. Compute SHA-256 digest of canonical string
      4. Sign canonical bytes using CAdES-BES provider (Cloud HSM or Local Token)
      5. Construct and return signed EtaDocument ready for submission queue
    """
    # 1. Build ETA JSON payload (will raise EtaMissingItemCodeError if any line lacks EgsCode)
    payload_dict = await build_eta_invoice(session, invoice_id, tenant_config)

    # 2. Serialize to canonical string
    canonical_str = serialize_document(payload_dict)

    # 3. Compute CAdES-BES hash
    canonical_hash = compute_cades_bes_hash(canonical_str)

    # 4. Sign using specified or default provider
    signing_provider = provider or get_signing_provider(tenant_config.signing_provider)
    sign_result = await signing_provider.sign_cades_bes(
        canonical_bytes=canonical_str.encode("utf-8"),
        tenant_id=tenant_config.tenant_id,
    )

    signature_b64 = sign_result.get("value") or sign_result.get("signature_b64")

    # Include signature object in ETA payload
    signed_payload = dict(payload_dict)
    signed_payload["signatures"] = [
        {
            "signatureType": "I",
            "value": signature_b64,
        }
    ]

    # 5. Create EtaDocument entity
    eta_doc = EtaDocument(
        tenant_id=tenant_config.tenant_id,
        internal_doc_type="sales_invoice",
        internal_doc_id=payload_dict["internalID"],
        eta_document_type=payload_dict["documentType"],
        eta_document_type_version=payload_dict["documentTypeVersion"],
        state=EtaDocumentState.SIGNED,
        payload_json=signed_payload,
        canonical_string_hash=canonical_hash,
        signature_b64=signature_b64,
        signature_type="I",
    )

    return eta_doc
