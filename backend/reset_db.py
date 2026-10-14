import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def reset_db():
    engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5434/omni_erp")
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS tenant CASCADE;"))
        await conn.execute(text("CREATE SCHEMA tenant;"))
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
    print("Reset successful")

if __name__ == "__main__":
    asyncio.run(reset_db())
