"""
setup_portal_test_data.py — one-off test fixture + token minting script for
live-verifying the new Client Portal frontend (Wave 3 item 5) in a browser,
without needing real WhatsApp/SMTP credentials configured (neither is set
up in this dev environment — confirmed via check_portal_setup.py).

What it does, against the FIRST tenant schema found:
  1. Picks (or tells you if none exists) a Contact and sets its phone_e164
     to a fixed test number, so /portal/auth/login can find it.
  2. Ensures that contact has at least one POSTED SalesInvoice with a line
     item, creating one if none exists, so /portal/invoices has something
     to show.
  3. Mints a portal JWT using the exact same algorithm as
     app.modules.portal.api.auth.create_portal_token (same SECRET_KEY,
     same payload shape: sub=contact_id, tenant_id, type=portal_access,
     24h expiry) — this is a TEST-ONLY shortcut standing in for the real
     OTP verify step, so the invoices/pay page can be exercised live
     without a configured WhatsApp/SMTP provider. It does not touch or
     bypass any production code path.

Prints the tenant_id, phone_e164, and the minted token so it can be
injected into the browser's sessionStorage for a live test of
GET /portal/invoices and POST /portal/invoices/{id}/pay.

Run from backend/ with: .venv\\Scripts\\python.exe setup_portal_test_data.py
"""
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

TEST_PHONE = "+201055501234"


def mint_portal_token(contact_id: str, tenant_id: str) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(hours=24)
    payload = {
        "sub": str(contact_id),
        "tenant_id": str(tenant_id),
        "type": "portal_access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        schemas = (await conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant_%' ORDER BY schema_name LIMIT 1"
        ))).scalars().all()
        if not schemas:
            print("No tenant schemas found.")
            return
        schema = schemas[0]
        tenant_id = schema.replace("tenant_", "").replace("_", "-")
        print("Using tenant schema:", schema, "-> tenant_id:", tenant_id)

        contact = (await conn.execute(text(
            f'SELECT id, name FROM "{schema}".contacts ORDER BY created_at LIMIT 1'
        ))).mappings().first()
        if not contact:
            print(f"No contacts found in {schema} — create one via the UI first.")
            return

        contact_id = contact["id"]
        print("Using contact:", contact["name"], contact_id)

        await conn.execute(text(
            f'UPDATE "{schema}".contacts SET phone_e164 = :phone WHERE id = :id'
        ), {"phone": TEST_PHONE, "id": contact_id})
        print("Set phone_e164 =", TEST_PHONE)

        existing_invoice = (await conn.execute(text(
            f'SELECT id, invoice_number FROM "{schema}".sales_invoices '
            f"WHERE contact_id = :cid AND status = 'POSTED' LIMIT 1"
        ), {"cid": contact_id})).mappings().first()

        if existing_invoice:
            print("Contact already has a POSTED invoice:", dict(existing_invoice))
        else:
            invoice_id = uuid4()
            invoice_number = f"PORTAL-TEST-{str(invoice_id)[:8]}"
            line_id = uuid4()
            item_id = uuid4()

            # NOTE: SalesInvoice has TWO separate lifecycle columns —
            # `status` (SalesInvoiceStatus: DRAFT/POSTED/PAID/CANCELLED,
            # this module's own field, what the portal query filters on)
            # AND `state` (DocumentState, from DocumentLifecycleMixin,
            # NOT NULL with no DB-level server_default). Both must be set
            # explicitly on a raw INSERT or Postgres rejects it.
            await conn.execute(text(f"""
                INSERT INTO "{schema}".sales_invoices
                    (id, created_at, updated_at, invoice_number, contact_id, status, state,
                     issue_date, due_date, currency, subtotal, tax_total, grand_total)
                VALUES
                    (:id, now(), now(), :invoice_number, :contact_id, 'POSTED', 'POSTED',
                     CURRENT_DATE, CURRENT_DATE + INTERVAL '14 days', 'EGP',
                     1000.0000, 140.0000, 1140.0000)
            """), {"id": invoice_id, "invoice_number": invoice_number, "contact_id": contact_id})

            await conn.execute(text(f"""
                INSERT INTO "{schema}".sales_invoice_lines
                    (id, created_at, updated_at, invoice_id, item_id,
                     qty, unit_price, line_total, tax_rate, tax_amount)
                VALUES
                    (:id, now(), now(), :invoice_id, :item_id,
                     1, 1000.0000, 1000.0000, 0.1400, 140.0000)
            """), {"id": line_id, "invoice_id": invoice_id, "item_id": item_id})

            print("Created POSTED test invoice:", invoice_number, invoice_id)

    await engine.dispose()

    token = mint_portal_token(str(contact_id), tenant_id)
    print("\n--- Portal test session ---")
    print("tenant_id:", tenant_id)
    print("phone_e164:", TEST_PHONE)
    print("portal token:\n", token)


if __name__ == "__main__":
    asyncio.run(main())
