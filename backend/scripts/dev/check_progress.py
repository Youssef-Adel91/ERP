import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def get_count():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5434/omni_erp')
    async with engine.connect() as conn:
        res = await conn.execute(text('SELECT COUNT(*) FROM tenant.cost_consumptions'))
        print(f'Consumptions processed: {res.scalar()}')
    await engine.dispose()

asyncio.run(get_count())
