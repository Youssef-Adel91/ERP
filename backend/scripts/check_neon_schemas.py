import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"))
        schemas = [row[0] for row in res.fetchall()]
        print("Schemas existing on DB:", schemas)

        res2 = await conn.execute(text("SELECT schema_name FROM public.tenants"))
        db_tenants = [row[0] for row in res2.fetchall()]
        print("Tenants in public.tenants:", db_tenants)
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
