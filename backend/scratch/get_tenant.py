import asyncio
from sqlalchemy import text
from app.core.db.database import engine

async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT id, schema_name FROM public.tenants LIMIT 1'))
        print(result.fetchone())

asyncio.run(main())
