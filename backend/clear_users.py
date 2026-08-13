"""
clear_users.py - Deletes ALL tenants, users, and their schemas from Neon DB.
Run from ERP/backend/ directory:
    python clear_users.py
"""

import asyncio
import os
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

import asyncpg


async def main():
    # Convert SQLModel URL to raw asyncpg URL
    raw_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    print("[*] Connecting to Neon Postgres...")
    conn = await asyncpg.connect(raw_url)

    try:
        # 1. List all tenant schemas
        schemas = await conn.fetch("""
            SELECT schema_name FROM information_schema.schemata
            WHERE schema_name LIKE 'tenant_%'
        """)
        print(f"\n[*] Found {len(schemas)} tenant schema(s):")
        for s in schemas:
            print(f"    - {s['schema_name']}")

        # 2. Drop each tenant schema (CASCADE removes all tables inside)
        for s in schemas:
            name = s["schema_name"]
            await conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
            print(f"    [OK] Dropped schema: {name}")

        # 3. Delete tenant_users first (FK dependency)
        try:
            r = await conn.execute("DELETE FROM public.tenant_users")
            print(f"\n[*] Deleted tenant_users: {r}")
        except Exception as e:
            print(f"[!] tenant_users not found or already empty: {e}")

        # 4. Delete users
        r = await conn.execute("DELETE FROM public.users")
        print(f"[*] Deleted users: {r}")

        # 5. Delete tenants
        r = await conn.execute("DELETE FROM public.tenants")
        print(f"[*] Deleted tenants: {r}")

        print("\n[OK] Database cleared successfully!")
        print("     Now register fresh at: http://localhost:3001/register")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        raise
    finally:
        await conn.close()
        print("[*] Connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
