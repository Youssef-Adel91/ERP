import asyncio
from app.core.db.database import AsyncSessionLocal
from app.modules.system.models import User
from sqlalchemy import delete

async def main():
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(delete(User))
            await session.commit()
            print(f"Deleted {result.rowcount} user(s) from public.users.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
