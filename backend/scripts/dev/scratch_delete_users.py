import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv
import os

load_dotenv()
url = os.getenv('DATABASE_URL')
print(f"Connecting to {url.split('@')[1] if '@' in url else url} ...")

async def delete_users():
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            print('Deleting users and tenants...')
            await conn.execute(text('TRUNCATE TABLE "users" CASCADE;'))
            print('Users deleted.')
    except Exception as e:
        print("Error:", e)
    finally:
        await engine.dispose()

asyncio.run(delete_users())
