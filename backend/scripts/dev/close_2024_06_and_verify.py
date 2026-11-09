"""
close_2024_06_and_verify.py — deterministically close period 2024-06 and
prove it with a raw SQL read immediately after (not the UI, which may show
cached state), so the next run of verify_item4_closed_period_rejection.py
starts from a known, confirmed-CLOSED state.

Usage (from backend/, same venv as the other scripts):
    python close_2024_06_and_verify.py
"""
import asyncio
import os
import uuid

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = os.environ["DATABASE_URL"]
SCHEMA = "tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f"
TARGET_PERIOD_ID = "3369ee21-c53c-4597-8993-277c0a89618f"


async def main():
    engine = create_async_engine(DATABASE_URL, future=True)
    translated_engine = engine.execution_options(schema_translate_map={"tenant": SCHEMA})
    Session = async_sessionmaker(translated_engine, expire_on_commit=False, class_=AsyncSession)

    from app.modules.accounting.service import close_period, PeriodAlreadyClosedError

    async with Session() as db:
        try:
            period = await close_period(uuid.UUID(TARGET_PERIOD_ID), uuid.uuid4(), db)
            print(f"close_period() returned: is_closed={period.is_closed} closed_at={period.closed_at}")
        except PeriodAlreadyClosedError as e:
            print(f"Already closed (no-op): {e}")
            await db.rollback()

    await engine.dispose()

    # Independent raw-SQL confirmation, bypassing the ORM/app entirely
    engine2 = create_async_engine(DATABASE_URL, future=True)
    async with engine2.connect() as conn:
        row = (
            await conn.execute(
                text(
                    f'SELECT is_closed, closed_by, closed_at FROM "{SCHEMA}".accounting_periods '
                    f"WHERE id = :id"
                ),
                {"id": TARGET_PERIOD_ID},
            )
        ).first()
        print(f"\nRAW SQL confirmation: is_closed={row[0]} closed_by={row[1]} closed_at={row[2]}")
    await engine2.dispose()


if __name__ == "__main__":
    asyncio.run(main())
