import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        try:
            await conn.execute(text("ALTER TABLE tenant_1612bc36_7e63_42c1_add9_2d63cb81d976.document_sequences ADD COLUMN IF NOT EXISTS document_type VARCHAR(50) DEFAULT '' NOT NULL"))
            print('Added document_type')
        except Exception as e:
            print('document_type error:', e)

        try:
            await conn.execute(text("ALTER TABLE tenant_1612bc36_7e63_42c1_add9_2d63cb81d976.eta_documents ADD COLUMN IF NOT EXISTS eta_document_type VARCHAR(1) DEFAULT '' NOT NULL"))
            await conn.execute(text("ALTER TABLE tenant_1612bc36_7e63_42c1_add9_2d63cb81d976.eta_documents ADD COLUMN IF NOT EXISTS eta_document_type_version VARCHAR(10) DEFAULT '' NOT NULL"))
            print('Added eta_documents columns')
        except Exception as e:
            print('eta_documents error:', e)
            
        await conn.commit()
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
