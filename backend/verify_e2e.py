"""
verify_e2e.py — Omni ERP End-to-End API Verification Script

Usage (from ERP/backend or anywhere with httpx installed):
    python verify_e2e.py

What it tests:
    1. API liveness check (GET /health)
    2. Tenant registration  (POST /api/v1/auth/register)
    3. Active plugins fetch (GET /api/v1/system/plugins/active)
    4. /me endpoint         (GET /api/v1/auth/me)
    5. Cleanup              (prints tenant_id for manual DB inspection)
"""
import io
import sys
import uuid

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8000"
API      = f"{BASE_URL}/api/v1"

# Unique test credentials so re-runs don't collide on the email uniqueness check
_uid = str(uuid.uuid4())[:8]
TEST_PAYLOAD = {
    "company_name": f"شركة الاختبار {_uid}",
    "full_name":    f"Test Admin {_uid}",
    "email":        f"e2e-test-{_uid}@omni-erp.dev",
    "password":     "TestPass1",
}

PASS = "✅"
FAIL = "❌"
INFO = "ℹ️ "

# ── Helpers ───────────────────────────────────────────────────────────────────

def step(n: int, title: str) -> None:
    print(f"\n{'=' * 55}")
    print(f"  Step {n}: {title}")
    print(f"{'=' * 55}")

def ok(msg: str) -> None:
    print(f"  [OK]  {msg}")

def fail(msg: str) -> None:
    print(f"  [!!]  {msg}")

def info(msg: str) -> None:
    print(f"  [ii]  {msg}")

def abort(msg: str) -> None:
    fail(msg)
    print(f"\n{'=' * 55}")
    print("  RESULT: E2E TEST FAILED -- fix the error above and retry.")
    print(f"{'=' * 55}\n")
    sys.exit(1)

# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> None:
    print(f"\n{'=' * 55}")
    print("  Omni ERP -- End-to-End API Verification")
    print(f"{'=' * 55}")
    info(f"Target: {BASE_URL}")
    info(f"Test email: {TEST_PAYLOAD['email']}")

    client = httpx.Client(timeout=15.0)

    # ── Step 1: Health check ──────────────────────────────────────────────────
    step(1, "API Liveness (GET /health)")
    try:
        r = client.get(f"{BASE_URL}/health")
        if r.status_code == 200:
            ok(f"API is alive — status={r.status_code}, body={r.json()}")
        else:
            abort(f"Health check returned HTTP {r.status_code}: {r.text}")
    except httpx.ConnectError:
        abort(
            "Cannot connect to http://localhost:8000.\n"
            "  → Is the FastAPI server running? (check the backend terminal window)",
        )

    # ── Step 2: Register a new tenant ─────────────────────────────────────────
    step(2, "Tenant Registration (POST /api/v1/auth/register)")
    r = client.post(f"{API}/auth/register", json=TEST_PAYLOAD)

    if r.status_code == 201:
        data = r.json()
        ok(f"Tenant created!  tenant_id  = {data['tenant_id']}")
        ok(f"                 schema     = {data['schema_name']}")
        ok(f"                 user_id    = {data['user_id']}")
        access_token  = data["access_token"]
        tenant_id     = data["tenant_id"]
    elif r.status_code == 409:
        abort(
            f"409 Conflict — email already registered.\n"
            f"  Detail: {r.json().get('detail')}\n"
            f"  → The test email '{TEST_PAYLOAD['email']}' exists. This should not\n"
            f"    happen because we generate a UUID suffix. Check your DB state.",
        )
    elif r.status_code == 422:
        abort(
            f"422 Validation Error — payload rejected by FastAPI.\n"
            f"  Detail: {r.json().get('detail')}",
        )
    else:
        abort(f"Unexpected HTTP {r.status_code}: {r.text[:400]}")

    # ── Step 3: Active plugins ────────────────────────────────────────────────
    step(3, "Active Plugins (GET /api/v1/system/plugins/active)")
    headers = {"Authorization": f"Bearer {access_token}"}
    r = client.get(f"{API}/system/plugins/active", headers=headers)

    if r.status_code == 200:
        plugins: list = r.json().get("active_plugins", [])
        if plugins:
            ok(f"Plugins endpoint returned: {plugins}")
            if "accounting" in plugins and "contacts" in plugins:
                ok("Universal Core defaults confirmed → ['accounting', 'contacts'] ✓")
            else:
                fail(
                    f"Expected ['accounting','contacts'] in defaults, got: {plugins}\n"
                    f"  → Check Tenant.active_plugins default_factory in models.py",
                )
        else:
            fail(
                "active_plugins is empty [].\n"
                "  → The column exists but default_factory did not seed ['accounting','contacts'].\n"
                "  → Did you run `alembic upgrade head` AFTER the model change?\n"
                "  → Or does the new tenant row have a NULL/empty value?",
            )
    elif r.status_code == 401:
        abort(
            "401 Unauthorized — JWT was not accepted.\n"
            "  → Token from /register is not valid for /system/plugins/active.\n"
            "  → Check that SECRET_KEY in .env matches the running server's env.",
        )
    elif r.status_code == 403:
        abort("403 Forbidden — the test user does not have the required roles.")
    else:
        abort(f"Unexpected HTTP {r.status_code}: {r.text[:400]}")

    # ── Step 4: /me endpoint ──────────────────────────────────────────────────
    step(4, "User Profile (GET /api/v1/auth/me)")
    r = client.get(f"{API}/auth/me", headers=headers)

    if r.status_code == 200:
        me = r.json()
        ok(f"User  id        = {me.get('id')}")
        ok(f"      email     = {me.get('email')}")
        ok(f"      roles     = {me.get('roles')}")
        ok(f"      plugins   = {me.get('active_plugins')}")
    else:
        fail(f"/me returned HTTP {r.status_code}: {r.text[:200]}")

    # -- Summary
    print(f"\n{'=' * 55}")
    print("  [OK] ALL STEPS PASSED -- E2E Flow is Working!")
    print(f"{'=' * 55}")
    print(f"  tenant_id     : {tenant_id}")
    print(f"  active_plugins: {plugins}")
    print(
        "\n  Next: open http://localhost:3000/register in your browser,\n"
        "  register using a NEW email, then check the sidebar shows\n"
        "  only Accounting + Contacts sections.\n",
    )
    client.close()


if __name__ == "__main__":
    run()
