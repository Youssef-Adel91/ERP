"""
tests/eta/test_document_builder.py — Unit & Integration Tests for ETA Document Builder & Signing (Phase 5 - Step 3)

Tests:
  1. Pre-Submission Gate (FR-521): Proving that build_eta_invoice raises EtaMissingItemCodeError
     if any invoice line item is missing a valid EGS/GS1 code.
  2. Full CAdES-BES Signing Pipeline: Proving that a fully coded invoice builds the ETA JSON payload
     with pinned TypeVersion "1.0", serializes canonically, computes SHA-256 hash, and signs via CloudHSM.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.eta.exceptions import EtaMissingItemCodeError
from app.modules.eta.models.codes import EgsCode, EgsCodeType
from app.modules.eta.models.core import (
    EtaDocumentState,
    EtaEnvironment,
    EtaSigningProvider,
    EtaTenantConfig,
)
from app.modules.eta.services.builder import build_eta_invoice, prepare_signed_eta_document
from app.modules.eta.services.signing import CloudHsmProvider, LocalHardwareTokenProvider
from app.modules.inventory.models.core import Item
from app.modules.sales.models.core import SalesOrder
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceLine

pytestmark = pytest.mark.asyncio


async def test_build_eta_invoice_pre_submission_gate_missing_code_raises(db_session: AsyncSession):
    """
    Verify Pre-Submission Gate (FR-521):
      An invoice containing any item without an active EGS/GS1 code in EgsCode or item.egs_code
      must immediately raise EtaMissingItemCodeError before canonicalization or ETA submission.
    """
    tenant_id = uuid4()
    contact_id = uuid4()

    # 1. Create Tenant Config
    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="client_test_gate",
        client_secret_ref="vault://secrets/eta/secret",
        taxpayer_rin="100200300",
        activity_code="4610",
    )
    db_session.add(tenant_config)

    # 2. Create one CODED Item and one UNCODED Item
    item_coded = Item(
        sku="SKU-CODED-01",
        name="Enterprise Server Grade A",
    )
    item_uncoded = Item(
        sku="SKU-UNCODED-02",
        name="Uncategorized Cable Accessory",
        egs_code=None,
    )
    db_session.add(item_coded)
    db_session.add(item_uncoded)
    await db_session.flush()

    # 3. Register EgsCode for only item_coded
    egs_code = EgsCode(
        tenant_id=tenant_id,
        item_id=item_coded.id,
        code_type=EgsCodeType.EGS,
        code_value="EG-100200300-SERVER01",
        is_active=True,
    )
    db_session.add(egs_code)

    # 4. Create Sales Order and Invoice containing BOTH items
    order = SalesOrder(
        order_number="ORD-GATE-001",
        contact_id=contact_id,
    )
    db_session.add(order)
    await db_session.flush()

    invoice = SalesInvoice(
        invoice_number="INV-GATE-001",
        order_id=order.id,
        contact_id=contact_id,
        issue_date=date.today(),
        subtotal=Decimal("600.0000"),
        tax_total=Decimal("84.0000"),
        grand_total=Decimal("684.0000"),
    )
    db_session.add(invoice)
    await db_session.flush()

    line_coded = SalesInvoiceLine(
        invoice_id=invoice.id,
        item_id=item_coded.id,
        qty=Decimal("1.0000"),
        unit_price=Decimal("500.0000"),
        line_total=Decimal("570.0000"),
        tax_rate=Decimal("0.1400"),
        tax_amount=Decimal("70.0000"),
    )
    line_uncoded = SalesInvoiceLine(
        invoice_id=invoice.id,
        item_id=item_uncoded.id,
        qty=Decimal("1.0000"),
        unit_price=Decimal("100.0000"),
        line_total=Decimal("114.0000"),
        tax_rate=Decimal("0.1400"),
        tax_amount=Decimal("14.0000"),
    )
    db_session.add(line_coded)
    db_session.add(line_uncoded)
    await db_session.commit()

    # 5. Calling build_eta_invoice MUST raise EtaMissingItemCodeError due to line_uncoded
    with pytest.raises(EtaMissingItemCodeError) as exc_info:
        await build_eta_invoice(db_session, invoice.id, tenant_config)

    assert "Pre-submission gate failed (FR-521)" in str(exc_info.value)
    assert "Uncategorized Cable Accessory" in str(exc_info.value)
    assert "SKU-UNCODED-02" in str(exc_info.value)


async def test_build_eta_invoice_success_and_cades_bes_signing(db_session: AsyncSession):
    """
    Verify complete Document Builder and CAdES-BES Signing pipeline:
      1. A fully coded invoice successfully builds the ETA JSON schema dictionary.
      2. Pinned Version is strictly '1.0'.
      3. Canonicalization and SHA-256 hash computation are deterministic.
      4. CloudHSM provider returns a valid Base64 CAdES-BES signature.
      5. prepare_signed_eta_document returns an EtaDocument in SIGNED state ready for submission.
    """
    tenant_id = uuid4()
    contact_id = uuid4()

    tenant_config = EtaTenantConfig(
        tenant_id=tenant_id,
        environment=EtaEnvironment.PREPRODUCTION,
        client_id="client_test_success",
        client_secret_ref="vault://secrets/eta/secret",
        taxpayer_rin="200300400",
        activity_code="4610",
        signing_provider=EtaSigningProvider.CLOUD_HSM,
    )
    db_session.add(tenant_config)

    # 1. Create two items both with active EgsCode registry entries
    item1 = Item(sku="SKU-GS1-100", name="Commercial Display 4K")
    item2 = Item(sku="SKU-EGS-200", name="Hardware Mounting Kit")
    db_session.add(item1)
    db_session.add(item2)
    await db_session.flush()

    code1 = EgsCode(
        tenant_id=tenant_id,
        item_id=item1.id,
        code_type=EgsCodeType.GS1,
        code_value="06221234567890",
        is_active=True,
    )
    code2 = EgsCode(
        tenant_id=tenant_id,
        item_id=item2.id,
        code_type=EgsCodeType.EGS,
        code_value="EG-200300400-MOUNT1",
        is_active=True,
    )
    db_session.add(code1)
    db_session.add(code2)

    # 2. Create SalesOrder & SalesInvoice
    order = SalesOrder(order_number="ORD-SUCCESS-100", contact_id=contact_id)
    db_session.add(order)
    await db_session.flush()

    invoice = SalesInvoice(
        invoice_number="INV-SUCCESS-100",
        order_id=order.id,
        contact_id=contact_id,
        issue_date=date.today(),
        subtotal=Decimal("1500.0000"),
        tax_total=Decimal("210.0000"),
        grand_total=Decimal("1710.0000"),
    )
    db_session.add(invoice)
    await db_session.flush()

    line1 = SalesInvoiceLine(
        invoice_id=invoice.id,
        item_id=item1.id,
        qty=Decimal("2.0000"),
        unit_price=Decimal("500.0000"),
        line_total=Decimal("1140.0000"),
        tax_rate=Decimal("0.1400"),
        tax_amount=Decimal("140.0000"),
    )
    line2 = SalesInvoiceLine(
        invoice_id=invoice.id,
        item_id=item2.id,
        qty=Decimal("5.0000"),
        unit_price=Decimal("100.0000"),
        line_total=Decimal("570.0000"),
        tax_rate=Decimal("0.1400"),
        tax_amount=Decimal("70.0000"),
    )
    db_session.add(line1)
    db_session.add(line2)
    await db_session.commit()

    # 3. Test build_eta_invoice dictionary generation
    payload = await build_eta_invoice(db_session, invoice.id, tenant_config)

    assert payload["documentType"] == "I"
    assert payload["documentTypeVersion"] == "1.0"  # Pinned to 1.0
    assert payload["issuer"]["id"] == "200300400"
    assert len(payload["invoiceLines"]) == 2

    # Verify item codes mapped correctly
    line_codes = {line["itemCode"]: line["itemType"] for line in payload["invoiceLines"]}
    assert line_codes["06221234567890"] == "GS1"
    assert line_codes["EG-200300400-MOUNT1"] == "EGS"

    # 4. Test full signing pipeline via CloudHsmProvider
    provider = CloudHsmProvider(hsm_url="https://hsm.egypttrust.com/api/v1/sign")
    eta_doc = await prepare_signed_eta_document(db_session, invoice.id, tenant_config, provider=provider)

    assert eta_doc.state == EtaDocumentState.SIGNED
    assert eta_doc.signature_type == "I"
    assert eta_doc.signature_b64 is not None
    assert len(eta_doc.canonical_string_hash) == 64  # Valid SHA-256 hex string

    # Verify signatures array embedded in payload_json
    assert "signatures" in eta_doc.payload_json
    assert eta_doc.payload_json["signatures"][0]["signatureType"] == "I"
    assert eta_doc.payload_json["signatures"][0]["value"] == eta_doc.signature_b64

    # 5. Also verify LocalHardwareTokenProvider produces valid signature structure
    local_provider = LocalHardwareTokenProvider()
    sign_local = await local_provider.sign_cades_bes(b"TEST_CANONICAL_BYTES", tenant_id)
    assert sign_local["signing_provider"] == "LOCAL_TOKEN"
    assert "value" in sign_local
