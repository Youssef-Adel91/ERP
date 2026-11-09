"""
check_portal_setup.py — one-off diagnostic to see whether the Client Portal
frontend can be live-tested end to end in this dev environment.

Checks, without printing secrets:
  1. Is SMTP configured (email fallback delivery for the OTP)?
  2. Is a WhatsApp provider configured for any tenant (primary delivery)?
  3. Does any Contact in the first tenant schema already have phone_e164
     set (a prerequisite for /portal/auth/login to find them at all)?
  4. Does that contact (if any) have a POSTED SalesInvoice to actually
     view/pay in the portal?

Run from backend/ with: .venv\\Scripts\\python.exe check_portal_setup.py
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings


async def main():
    print("SMTP configured:", bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL))
    print("SMTP_HOST set:", bool(settings.SMTP_HOST))

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        schemas = (await conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant_%' ORDER BY schema_name"
        ))).scalars().all()
        print("Tenant schemas found:", len(schemas))

        for schema in schemas:
            contacts_with_phone = (await conn.execute(text(
                f'SELECT id, name, phone_e164, email FROM "{schema}".contacts '
                f"WHERE phone_e164 IS NOT NULL AND phone_e164 != '' LIMIT 5"
            ))).mappings().all()
            if contacts_with_phone:
                print(f"\n--- {schema} — contacts with phone_e164 ---")
                for c in contacts_with_phone:
                    print(dict(c))
                    posted_invoices = (await conn.execute(text(
                        f'SELECT id, invoice_number, status, grand_total, currency '
                        f'FROM "{schema}".sales_invoices '
                        f"WHERE contact_id = :cid AND status = 'POSTED' LIMIT 5"
                    ), {"cid": c["id"]})).mappings().all()
                    print("  POSTED invoices for this contact:", [dict(i) for i in posted_invoices])

        # Also check whatsapp config table if it exists
        wa_configured = (await conn.execute(text(
            "SELECT COUNT(1) FROM information_schema.tables "
            "WHERE table_name ILIKE '%whatsapp%'"
        ))).scalar()
        print("\nTables matching '%whatsapp%':", wa_configured)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
