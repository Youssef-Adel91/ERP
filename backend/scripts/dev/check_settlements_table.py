import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        schema = "tenant_5410d254_bb21_4d00_a153_0acf49945bb4"
        r1 = await conn.execute(
            text(
                "SELECT COUNT(1) FROM information_schema.tables "
                "WHERE table_name = 'finance_carrier_settlements' AND table_schema = :s"
            ),
            {"s": schema},
        )
        print("table exists in", schema, ":", r1.scalar() > 0)

        r2 = await conn.execute(text("SHOW search_path"))
        print("connection default search_path:", r2.scalar())

        r3 = await conn.execute(
            text(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'finance_carrier_settlements'"
            )
        )
        print("all schemas containing finance_carrier_settlements:", [row[0] for row in r3.fetchall()])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
