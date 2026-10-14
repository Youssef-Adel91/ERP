import asyncio
import sys
from sqlalchemy import text
from app.core.db.database import engine

async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT name, slug, schema_name, status FROM public.tenants ORDER BY name'))
        rows = result.fetchall()
        for row in rows:
            line = f"name={row[0]!r}  slug={row[1]!r}  schema={row[2]!r}  status={row[3]!r}"
            sys.stdout.buffer.write((line + "\n").encode("utf-8"))

asyncio.run(main())
