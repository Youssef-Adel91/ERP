import asyncio
from app.core.db.database import AsyncSessionLocal
from sqlalchemy import text

async def delete_users():
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM public.users CASCADE;"))
        await session.commit()
        print("All users deleted successfully.")

if __name__ == "__main__":
    asyncio.run(delete_users())
