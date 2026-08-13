import asyncio
import os
import sys
import subprocess

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.environ["DATABASE_URL"]

async def main():
    engine = create_async_engine(
        DATABASE_URL,
        future=True,
    )

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'tenant_%'"))
        schemas = [row[0] for row in result.all()]
    
    await engine.dispose()
    
    print(f"Found {len(schemas)} tenant schemas.")
    for schema in schemas:
        print(f"\n--- Upgrading schema: {schema} ---")
        # Run alembic upgrade head for this schema
        try:
            subprocess.run(
                [sys.executable, "-m", "alembic", "-n", "tenant", "-x", f"schema={schema}", "upgrade", "head"],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error upgrading {schema}: {e}")
            sys.exit(1)
            
    print("\nAll tenant schemas upgraded successfully.")

if __name__ == "__main__":
    asyncio.run(main())
