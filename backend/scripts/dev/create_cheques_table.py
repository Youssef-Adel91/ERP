import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.db.base import TenantBase
import app.modules.contacts.models
import app.modules.sales.models
import app.modules.inventory.models
import app.modules.finance.models
import app.modules.eta.models
# import other models so they don't get inadvertently created or cause issues?
# TenantBase.metadata.create_all will only create missing tables.

async def main():
    url = os.environ['DATABASE_URL']
    if not url.startswith('postgresql+asyncpg://'):
        url = url.replace('postgresql://', 'postgresql+asyncpg://')
        
    engine = create_async_engine(url, echo=True)
    engine = engine.execution_options(schema_translate_map={'tenant': 'tenant_1612bc36_7e63_42c1_add9_2d63cb81d976'})
    
    async with engine.begin() as conn:
        from sqlalchemy import text
        table_exists = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'tenant_1612bc36_7e63_42c1_add9_2d63cb81d976' AND table_name = 'cheques'"
        ))
        if not table_exists.scalar():
            print('Creating Cheque table...')
            await conn.run_sync(TenantBase.metadata.create_all)
            print('Cheque table created.')
        else:
            print('Cheque table already exists.')
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())
