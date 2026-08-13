import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def check_user():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT email, is_active FROM public.users"))
        users = result.fetchall()
        print('Users in DB:')
        for u in users:
            print(f' - {u[0]} (active: {u[1]})')

asyncio.run(check_user())
