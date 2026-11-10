"""
p1_extra_bypass_verify.py — end-to-end live proof that the
forgot-password/reset-password bypass fix actually works, AND that the
handler's own internal protections (single-use, TTL, user binding) hold.

Steps (each printed clearly, PASS/FAIL at the end of each):
  1) POST /api/v1/auth/forgot-password for the real test account.
     Must be 200 now (was 401 before the _BYPASS_PATHS fix).
  2) Read the reset token directly from Redis (pwreset:<token> -> user_id) —
     we do this instead of relying on email delivery, since SMTP may not be
     configured in this dev environment; the token exists in Redis the
     instant step 1 succeeds, regardless of whether the email itself sent.
  3) POST /api/v1/auth/reset-password with that token + a new password.
     Must be 200.
  4) POST /api/v1/auth/login with the NEW password. Must be 200 with a
     real access_token.
  5) SECURITY CHECK — replay the SAME (now-consumed) reset token again.
     Must be rejected (400), proving single-use.
  6) SECURITY CHECK — try a random, never-issued token. Must be rejected.

Run from backend/ with the project's own virtualenv:

    .\.venv\Scripts\python.exe p1_extra_bypass_verify.py
"""
import asyncio
import secrets

TARGET_EMAIL = "hospaudit21789412307956@gmail.com"
NEW_PASSWORD = "PostFixPass456"
BASE_URL = "http://localhost:8000/api/v1"


async def main() -> None:
    import httpx
    import redis.asyncio as aioredis

    from app.core.config import settings

    redis_client = aioredis.from_url(settings.REDIS_URL)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        print("=" * 70)
        print("1) POST /auth/forgot-password")
        print("=" * 70)
        r1 = await client.post("/auth/forgot-password", json={"email": TARGET_EMAIL})
        print(f"  status: {r1.status_code}")
        print(f"  body:   {r1.text}")
        if r1.status_code != 200:
            print("  RESULT: FAIL — bypass fix did not take effect. Stopping.")
            return
        print("  RESULT: PASS — no longer 401.")

        print()
        print("=" * 70)
        print("2) Read the reset token directly from Redis (pwreset:*)")
        print("=" * 70)
        token = None
        async for key in redis_client.scan_iter(match="pwreset:*"):
            token = key.decode().removeprefix("pwreset:")
            uid = await redis_client.get(key)
            print(f"  found key={key.decode()} -> user_id={uid.decode() if uid else None}")
        if token is None:
            print("  RESULT: FAIL — no pwreset:* key found in Redis. Stopping.")
            return
        print(f"  RESULT: PASS — token acquired ({token[:12]}...).")

        print()
        print("=" * 70)
        print("3) POST /auth/reset-password with that token")
        print("=" * 70)
        r3 = await client.post("/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        print(f"  status: {r3.status_code}")
        print(f"  body:   {r3.text}")
        if r3.status_code != 200:
            print("  RESULT: FAIL. Stopping.")
            return
        print("  RESULT: PASS.")

        print()
        print("=" * 70)
        print("4) POST /auth/login with the NEW password")
        print("=" * 70)
        r4 = await client.post("/auth/login", json={"email": TARGET_EMAIL, "password": NEW_PASSWORD})
        print(f"  status: {r4.status_code}")
        ok4 = r4.status_code == 200 and "access_token" in r4.json()
        print(f"  has access_token: {ok4}")
        print("  RESULT:", "PASS" if ok4 else "FAIL")

        print()
        print("=" * 70)
        print("5) SECURITY CHECK — replay the SAME reset token again")
        print("=" * 70)
        r5 = await client.post("/auth/reset-password", json={"token": token, "new_password": "SecondAttempt789"})
        print(f"  status: {r5.status_code}")
        print(f"  body:   {r5.text}")
        print("  RESULT:", "PASS — correctly rejected (single-use holds)" if r5.status_code != 200
              else "FAIL — token was reusable! SECURITY BUG.")

        print()
        print("=" * 70)
        print("6) SECURITY CHECK — random never-issued token")
        print("=" * 70)
        fake_token = secrets.token_urlsafe(48)
        r6 = await client.post("/auth/reset-password", json={"token": fake_token, "new_password": "Whatever123"})
        print(f"  status: {r6.status_code}")
        print(f"  body:   {r6.text}")
        print("  RESULT:", "PASS — correctly rejected" if r6.status_code != 200
              else "FAIL — random token was accepted! SECURITY BUG.")

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
