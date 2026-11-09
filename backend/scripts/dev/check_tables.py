"""
check_tables.py - Check tables in tenant schema and run alembic migration if needed.
"""
import asyncio, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
load_dotenv()
import asyncpg

SCHEMA = "tenant_1612bc36_7e63_42c1_add9_2d63cb81d976"

async def main():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)

    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
        SCHEMA
    )
    print(f"\nTables in '{SCHEMA}' ({len(tables)}):")
    for t in sorted(tables, key=lambda r: r["table_name"]):
        print(f"  - {t['table_name']}")

    await conn.close()

asyncio.run(main())
