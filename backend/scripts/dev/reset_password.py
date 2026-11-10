"""
reset_password.py — one-off script to reset the password of the P0/P1 test
account (hospaudit21789412307956@gmail.com) directly in the local dev DB.

Run this from inside backend/ with the project's own virtualenv, e.g.:

    .\.venv\Scripts\python.exe reset_password.py

It reuses the app's own DATABASE_URL (from .env via app.core.config) and its
own bcrypt hashing function (app.core.security.security.hash_password), so
there is no separate DB client (psql/pgAdmin) to install or configure.
"""
import asyncio

# ── EDIT THIS if you want a different password ──────────────────────────────
NEW_PASSWORD = "TestOwner123"
TARGET_EMAIL = "hospaudit21789412307956@gmail.com"
# ──────────────────────────────────────────────────────────────────────────


async def main() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

    from app.core.config import settings
    from app.core.security.security import hash_password
    from app.modules.system.models import User

    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.email == TARGET_EMAIL.lower()))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"❌ No user found with email={TARGET_EMAIL}")
            return

        user.hashed_password = hash_password(NEW_PASSWORD)
        await session.commit()
        print(f"✅ Password for {TARGET_EMAIL} (tenant_id={user.tenant_id}) reset successfully.")
        print(f"   You can now log in with password: {NEW_PASSWORD}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
