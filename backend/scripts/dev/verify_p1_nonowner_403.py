#!/usr/bin/env python3
"""
verify_p1_nonowner_403.py

Live verification that a non-OWNER user CANNOT close or reopen an
accounting period (must get 403 from _OWNER_ONLY on both endpoints).

Per the governing prompt (prompt-p1-final-closure.md), the live UI has
no self-service way to add a second user to an existing tenant
(confirmed via browser: /dashboard/settings/team -> 404;
/dashboard/settings -> read-only account-info card only, no invite
flow). So this script creates the second user directly in the
`public.users` table via a raw-SQL insert, using the app's own
hash_password() (passlib/bcrypt) so the row is byte-for-byte what the
real /register or an admin-invite flow would have produced. This is
documented here explicitly as required by the prompt.

It does NOT forge a JWT by hand. It creates the DB row, then calls the
real, mounted POST /api/v1/auth/login endpoint with that account's
real credentials to obtain a genuinely server-issued token -- this
exercises the actual login code path, not just the token signing
function.

Steps:
  1. Insert a public.users row for tenant e1ee4d0e-e8d7-4d5d-9778-c8954687e63f
     with role=ADMIN (idempotent: delete-then-insert by fixed email, and
     safe to run twice).
  2. Also insert a matching tenant.tenant_users row for consistency
     (not strictly required for the JWT roles claim, which comes only
     from public.users.role -- but avoids surprising side effects
     elsewhere in the app that may expect a TenantUser row to exist).
  3. POST /api/v1/auth/login with that account's email+password.
  4. Find one genuinely OPEN period id and one genuinely CLOSED period
     id in the tenant (raw SQL against tenant.accounting_periods).
  5. POST /api/v1/accounting/periods/{open_id}/close as the ADMIN user
     -> print full status + body. MUST be 403.
  6. POST /api/v1/accounting/periods/{closed_id}/reopen as the ADMIN
     user -> print full status + body. MUST be 403.
  7. If either call returns 200: print a loud STOP banner and exit
     non-zero. Do not treat that as a pass under any framing.

Usage (from backend/, same venv as other verify_*.py scripts):
    python verify_p1_nonowner_403.py
"""

import asyncio
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.security.security import hash_password  # noqa: E402

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"

TENANT_ID = "e1ee4d0e-e8d7-4d5d-9778-c8954687e63f"
TENANT_SCHEMA = "tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f"

TEST_EMAIL = "p1-nonowner-403-test@nexuserp-security-check.com"
TEST_PASSWORD = "P1TestNonOwner!2026"
TEST_ROLE = "ADMIN"


async def upsert_public_user(engine) -> str:
    """Idempotent: delete any prior row for this email, then insert fresh."""
    new_id = str(uuid.uuid4())
    hashed = hash_password(TEST_PASSWORD)
    async with engine.begin() as conn:
        await conn.execute(
            text('DELETE FROM public.users WHERE email = :email'),
            {"email": TEST_EMAIL},
        )
        await conn.execute(
            text(
                '''
                INSERT INTO public.users
                    (id, tenant_id, email, hashed_password, full_name, role, is_active, is_superadmin)
                VALUES
                    (:id, :tenant_id, :email, :hashed_password, :full_name, :role, true, false)
                '''
            ),
            {
                "id": new_id,
                "tenant_id": TENANT_ID,
                "email": TEST_EMAIL,
                "hashed_password": hashed,
                "full_name": "P1 Non-Owner 403 Test",
                "role": TEST_ROLE,
            },
        )
    return new_id


async def upsert_tenant_user(engine, user_id: str) -> None:
    """Best-effort matching tenant.tenant_users row, for realism/consistency.
    Not required for the JWT roles-claim mechanism (confirmed by code
    reading: roles come only from public.users.role at login time).

    SELF-REPORTED CORRECTION: this step was originally written assuming
    a tenant.tenant_users table exists in every tenant schema. Live run
    against the real tenant schema failed with asyncpg.UndefinedTableError
    ("tenant_e1ee4d0e_...tenant_users does not exist"). A follow-up grep
    of backend/alembic confirmed no migration anywhere ever creates a
    tenant_users table in any tenant schema -- the TenantUser model in
    models.py is defined in code but was never actually migrated. This
    is consistent with (and reinforces) the earlier finding that the
    login/JWT path never reads TenantUser.role anyway. Since this step
    was already documented as non-essential to the security test, it is
    now skipped gracefully instead of failing the whole script."""
    async with engine.connect() as conn:
        exists_row = (
            await conn.execute(
                text(
                    '''
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = :schema AND table_name = 'tenant_users'
                    '''
                ),
                {"schema": TENANT_SCHEMA},
            )
        ).first()

    if not exists_row:
        print(
            f'  SKIPPED: "{TENANT_SCHEMA}".tenant_users does not exist '
            f"(no migration ever creates it -- TenantUser model is unmigrated/dead code). "
            f"Not required for the JWT roles-claim mechanism, so continuing without it."
        )
        return False

    new_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(f'DELETE FROM "{TENANT_SCHEMA}".tenant_users WHERE user_id = :user_id'),
            {"user_id": user_id},
        )
        await conn.execute(
            text(
                f'''
                INSERT INTO "{TENANT_SCHEMA}".tenant_users
                    (id, user_id, role, is_active)
                VALUES
                    (:id, :user_id, :role, true)
                '''
            ),
            {"id": new_id, "user_id": user_id, "role": TEST_ROLE},
        )
    return True


async def find_open_and_closed_period(engine) -> tuple[str, str]:
    async with engine.connect() as conn:
        open_row = (
            await conn.execute(
                text(
                    f'SELECT id FROM "{TENANT_SCHEMA}".accounting_periods '
                    f'WHERE is_closed = false ORDER BY id LIMIT 1'
                )
            )
        ).first()
        closed_row = (
            await conn.execute(
                text(
                    f'SELECT id FROM "{TENANT_SCHEMA}".accounting_periods '
                    f'WHERE is_closed = true ORDER BY id LIMIT 1'
                )
            )
        ).first()
    if not open_row:
        print("FATAL: no OPEN accounting period found in tenant. Cannot run close() test.")
        sys.exit(2)
    if not closed_row:
        print("FATAL: no CLOSED accounting period found in tenant. Cannot run reopen() test.")
        sys.exit(2)
    return str(open_row[0]), str(closed_row[0])


async def main() -> int:
    engine = create_async_engine(DATABASE_URL)
    try:
        print("=== Step 1: create/refresh non-OWNER (ADMIN) public.users row ===")
        user_id = await upsert_public_user(engine)
        print(f"  public.users row id={user_id} email={TEST_EMAIL} role={TEST_ROLE} tenant_id={TENANT_ID}")

        print("\n=== Step 2: create/refresh matching tenant.tenant_users row ===")
        created = await upsert_tenant_user(engine, user_id)
        if created:
            print(f"  tenant.tenant_users row created for user_id={user_id} role={TEST_ROLE}")

        print("\n=== Step 3: find one OPEN and one CLOSED period ===")
        open_id, closed_id = await find_open_and_closed_period(engine)
        print(f"  OPEN period id:   {open_id}")
        print(f"  CLOSED period id: {closed_id}")
    finally:
        await engine.dispose()

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n=== Step 4: POST /api/v1/auth/login as the ADMIN test user ===")
        login_resp = await client.post(
            f"{API}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        print(f"  status: {login_resp.status_code}")
        print(f"  body:   {login_resp.text}")
        if login_resp.status_code != 200:
            print("FATAL: login failed for the freshly created non-OWNER account. Cannot proceed.")
            return 2
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("\n=== Step 5: POST /api/v1/accounting/periods/{open_id}/close (ADMIN, OPEN period) ===")
        close_resp = await client.post(
            f"{API}/accounting/periods/{open_id}/close", headers=headers
        )
        print(f"  status: {close_resp.status_code}")
        print(f"  body:   {close_resp.text}")

        print("\n=== Step 6: POST /api/v1/accounting/periods/{closed_id}/reopen (ADMIN, CLOSED period) ===")
        reopen_resp = await client.post(
            f"{API}/accounting/periods/{closed_id}/reopen", headers=headers
        )
        print(f"  status: {reopen_resp.status_code}")
        print(f"  body:   {reopen_resp.text}")

    print("\n" + "=" * 60)
    close_ok = close_resp.status_code == 403
    reopen_ok = reopen_resp.status_code == 403

    if not close_ok or not reopen_ok:
        print("!!! STOP: SECURITY VULNERABILITY DETECTED !!!")
        if not close_ok:
            print(f"  close_period returned {close_resp.status_code} instead of 403 for a non-OWNER (ADMIN) caller.")
        if not reopen_ok:
            print(f"  reopen_period returned {reopen_resp.status_code} instead of 403 for a non-OWNER (ADMIN) caller.")
        print("Per the governing prompt: STOP immediately, do not proceed further.")
        print("=" * 60)
        return 1

    print("PASS: both close_period and reopen_period correctly returned 403 for a non-OWNER (ADMIN) caller.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
