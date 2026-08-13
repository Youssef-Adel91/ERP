import asyncio
from sqlalchemy import text
from app.core.db.database import engine

async def main():
    async with engine.begin() as c:
        await c.execute(text('DELETE FROM public.users CASCADE;'))
    print('Deleted all users.')

if __name__ == '__main__':
    asyncio.run(main())
