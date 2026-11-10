"""Tests for customer portal OTP flow, third-party integrations (Bosta/Mylerz, ETA, WhatsApp)."""
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db.database import _get_redis_client
from app.main import app
from app.modules.contacts.models import Contact, ContactType
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus


@pytest.mark.asyncio
async def test_portal_otp_login_and_invoices_flow(client, db_session):
    """
    1. Seed a test contact in the tenant DB.
    2. Step 1: POST /api/v1/portal/auth/login -> OTP generated and stored in Redis.
    3. Step 2: POST /api/v1/portal/auth/login/verify with correct OTP -> returns portal JWT.
    4. Call GET /api/v1/portal/invoices with portal JWT -> returns posted invoices.
    5. Call POST /api/v1/portal/invoices/{id}/pay -> 501 (payment disabled).
    """
    from tests.conftest import TEST_TENANT_ID

    contact_id = uuid4()
    phone = "+201012345678"
    contact = Contact(
        id=contact_id,
        name="Portal Customer",
        phone_e164=phone,
        contact_type=ContactType.CUSTOMER,
    )
    db_session.add(contact)

    # Seed an invoice for this contact
    inv_id = uuid4()
    invoice = SalesInvoice(
        id=inv_id,
        invoice_number="INV-PORTAL-001",
        contact_id=contact_id,
        issue_date=datetime.now(UTC),
        status=SalesInvoiceStatus.POSTED,
        subtotal=1000,
        tax_total=140,
        grand_total=1140,
        total_amount=1140,
    )
    db_session.add(invoice)
    await db_session.commit()

    @asynccontextmanager
    async def mock_tenant_session(_tid):
        yield db_session

    with patch("app.modules.portal.api.auth.tenant_session", mock_tenant_session), \
         patch("app.modules.portal.api.statements.tenant_session", mock_tenant_session):

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as unauth_client:
            # Step 1: Request OTP (mock notify_contact to simulate WhatsApp/Email gateway)
            mock_notify = AsyncMock(return_value="whatsapp")
            with patch("app.modules.portal.api.auth.notify_contact", mock_notify):
                login_res = await unauth_client.post(
                    "/api/v1/portal/auth/login",
                    json={"phone_e164": phone, "tenant_id": str(TEST_TENANT_ID)},
                )
                assert login_res.status_code == 200, login_res.text
                assert mock_notify.called
                otp_code = mock_notify.call_args.kwargs["whatsapp_parameters"][0]["text"]
                assert len(otp_code) == 6

            # Step 2: Verify OTP with WRONG code -> 401
            bad_verify = await unauth_client.post(
                "/api/v1/portal/auth/login/verify",
                json={"phone_e164": phone, "tenant_id": str(TEST_TENANT_ID), "otp_code": "000000"},
            )
            assert bad_verify.status_code == 401

            # Step 2: Verify OTP with CORRECT code -> 200 + token
            good_verify = await unauth_client.post(
                "/api/v1/portal/auth/login/verify",
                json={"phone_e164": phone, "tenant_id": str(TEST_TENANT_ID), "otp_code": otp_code},
            )
            assert good_verify.status_code == 200
            portal_token = good_verify.json()["access_token"]
            assert portal_token

        # Step 3: Access portal statements with portal token
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {portal_token}"},
        ) as portal_client:
            invoices_res = await portal_client.get("/api/v1/portal/invoices")
            assert invoices_res.status_code == 200
            invoices_list = invoices_res.json()
            assert len(invoices_list) >= 1
            assert any(i["id"] == str(inv_id) for i in invoices_list)

            # Step 4: Online pay -> returns 501 intentionally disabled
            pay_res = await portal_client.post(f"/api/v1/portal/invoices/{inv_id}/pay")
            assert pay_res.status_code == 501


@pytest.mark.asyncio
async def test_eta_e_invoicing_config_and_codes(client):
    """Verify ETA e-invoicing configuration and EGS codes management."""
    # 1. Update/Get ETA tenant config
    cfg_payload = {
        "client_id": "test-client-id",
        "client_secret_ref": "vault://eta-secret",
        "taxpayer_rin": "123456789",
        "activity_code": "4610",
        "environment": "PREPRODUCTION",
    }
    res_cfg = await client.put("/api/v1/eta/config", json=cfg_payload)
    assert res_cfg.status_code == 200, res_cfg.text
    assert res_cfg.json()["taxpayer_rin"] == "123456789"

    # 2. Register EGS code
    egs_payload = {
        "item_id": str(uuid4()),
        "code_value": "EG-111111111-ITEM01",
        "code_type": "EGS",
        "name_ar": "منتج اختباري",
        "name_en": "Test Product",
    }
    res_code = await client.post("/api/v1/eta/egs-codes", json=egs_payload)
    assert res_code.status_code in (200, 201)


@pytest.mark.asyncio
async def test_carrier_webhooks_and_shipping(client):
    """Verify carrier account setup and supported carriers listing."""
    # 1. Available carriers
    res_avail = await client.get("/api/v1/logistics/carriers/available")
    assert res_avail.status_code == 200
    carriers = res_avail.json()
    assert "bosta" in [c["code"] for c in carriers]

    # 2. Carrier account creation (Bosta sandbox)
    carrier_payload = {
        "carrier_code": "bosta",
        "credentials_ref": "vault://bosta-key",
        "webhook_secret_ref": "vault://bosta-secret",
        "is_active": True,
    }
    res_carrier = await client.post("/api/v1/logistics/carriers", json=carrier_payload)
    assert res_carrier.status_code in (200, 201)
