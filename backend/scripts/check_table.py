import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        schema = 'tenant_1612bc36_7e63_42c1_add9_2d63cb81d976'
        result = await conn.execute(text(
            "SELECT COUNT(1) FROM information_schema.tables WHERE table_name = 'document_sequences' AND table_schema = :s"
        ), {"s": schema})
        print(f"Exists in DB {schema}:", result.scalar() > 0)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
