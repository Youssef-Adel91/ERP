# Antigravity Round 2 — Trust Core ERP Report

> Branch: `security-hardening` | Date: 2026-11-10

---

## Summary

This report covers all work completed in the second autonomous Antigravity session on the Trust Core ERP repository. Every item in the Round 2 prompt has been addressed.

---

## 1. Test Suite Verification

### Backend — pytest

| Metric | Result |
|--------|--------|
| Total tests collected | **181** |
| Passed | **181** |
| Failed | **0** |
| Duration | **1m 52s** |

> **Note:** Tests require outbound network access to Neon (remote PostgreSQL). They must be run with `BypassSandbox: true` or directly in the terminal — the standard sandbox blocks outbound TCP and causes them to hang silently. All 181 tests pass cleanly once the network is available.

New test files committed this round:
- `backend/tests/test_portal_and_third_party.py` — Portal OTP login flow, ETA e-invoicing config & EGS codes, logistics carriers
- `backend/tests/test_provisioning_gate.py` — 503 holding gate, startup reconciler
- `backend/tests/test_router_role_gates.py` — 35 parametrised write-gate tests + user-creation endpoint

### Frontend — Next.js build

```
▲ Next.js 16.2.10 (Turbopack)
✓ Compiled successfully in 4.3s
✓ TypeScript passed
✓ 42 routes generated (40 static, 2 dynamic)
0 errors, 0 build warnings
```

---

## 2. Test Tenant Cleanup

| Item | Action |
|------|--------|
| `ui.test.round7@example.com` ("Test Co Seven") | Deleted |
| Schema `tenant_683d4514_8cd4_41f7_b85f_c4f97006b606` | Dropped |
| Script used | `backend/scripts/dev/cleanup_test_tenants.py` (guarded to `ui.test.*` only) |

---

## 3. Role Gates — Full Implementation

### New endpoint: `POST /api/v1/auth/users`

Restricted to `OWNER` and `ADMIN`. Accepts `email`, `full_name`, `password`, `role` and returns the created user. Prevents duplicate emails (409).

### Routers gated with `RequireRoleForWrites`

| Router | Allowed roles for writes | File |
|--------|--------------------------|------|
| Import dossiers | OWNER, ADMIN, ACCOUNTING | `modules/imports/api/dossiers.py` |
| POS | OWNER, ADMIN, STAFF, SALES | `modules/pos/api.py` |
| Stock take | OWNER, ADMIN, STAFF | `modules/inventory/api/stock_take.py` |
| Approvals requests | OWNER, ADMIN, ACCOUNTING, STAFF, SALES | `modules/approvals/api.py` |
| Approvals decide | OWNER, ADMIN, ACCOUNTING only | `modules/approvals/api.py` |
| Inventory items | OWNER, ADMIN, STAFF | `modules/inventory/api/items.py` |
| Inventory transfers | OWNER, ADMIN, STAFF | `modules/inventory/api/transfer.py` |
| Contacts | OWNER, ADMIN, STAFF, SALES, ACCOUNTING | `modules/contacts/router.py` |
| Vendor cases | OWNER, ADMIN, ACCOUNTING | `modules/cases/api/vendors.py` |
| Purchase orders | OWNER, ADMIN, STAFF, ACCOUNTING | `modules/purchasing/api/orders.py` |
| Landed cost allocation | OWNER, ADMIN, ACCOUNTING | `modules/purchasing/api/allocation.py` |
| Sales orders | OWNER, ADMIN, STAFF, SALES | `modules/sales/api/orders.py` |
| Sales invoices | OWNER, ADMIN, ACCOUNTING, SALES | `modules/sales/api/invoices.py` |
| Reporting | OWNER, ADMIN, ACCOUNTING | `modules/reporting/router.py` |
| Plugin inventory | OWNER, ADMIN, STAFF | `plugins/inventory/router.py` |
| Recruitment jobs | OWNER, ADMIN, STAFF | `plugins/recruitment/api.py` |
| Recruitment candidates | OWNER, ADMIN, STAFF | `plugins/recruitment/api_candidates.py` |
| Recruitment interviews | OWNER, ADMIN, STAFF | `plugins/recruitment/api_interviews.py` |
| Travel bookings | OWNER, ADMIN, STAFF, SALES | `plugins/travel/api.py` |
| Travel packages | OWNER, ADMIN, STAFF, SALES | `plugins/travel/api_packages.py` |
| Travel passengers | OWNER, ADMIN, STAFF, SALES | `plugins/travel/api_passengers.py` |
| Travel visas | OWNER, ADMIN, STAFF, SALES | `plugins/travel/api_visas.py` |

**Rule:** reads (`GET`, `HEAD`, `OPTIONS`) are never blocked. Only state-changing methods (`POST`, `PUT`, `PATCH`, `DELETE`) require role.

---

## 4. Auth Security Architecture

Documented in full in [`docs/SECURITY.md`](SECURITY.md). Key points:

- **Current state:** access token and refresh token both stored in `localStorage`. Risk level: HIGH (XSS exposure).
- **Recommended architecture (phased BFF):** Move refresh token to httpOnly `SameSite=Lax` cookie, keep access token in memory only (Zustand, not persisted).
- **Why not done now:** Cross-origin localhost constraint (`:3000` vs `:8000`) prevents cookie sharing without a same-origin BFF proxy; a half-implementation is riskier than a documented plan.
- **What's safe today:** Short-lived access tokens (15 min), Redis-backed refresh token revocation on logout, bcrypt hashing, rate limiting on auth endpoints.

---

## 5. Provisioning Performance

### Before
~240 seconds (2 connections × ~120 sequential `CREATE TABLE` round-trips to Neon over WAN).

### After
**~7 seconds** — PL/pgSQL template cloning via `CREATE TABLE ... (LIKE template.t INCLUDING ALL)` runs entirely inside the PostgreSQL engine on a single network round-trip.

### Implementation details (`app/core/db/database.py`)
1. A `tenant_template` schema is pre-built once with all 91 tables, indexes, constraints, and 51 foreign keys.
2. `_provision_tenant_schema_internal()` now runs a single `DO $$ ... $$` PL/pgSQL block that iterates the template schema and clones each table, then re-adds foreign keys — all in one transaction, one round-trip.
3. Startup reconciler (`reconcile_orphaned_provisioning`) re-queues any `tenant:provisioning:<id>` Redis key that survived a server restart.
4. 503 gate returns `TENANT_PROVISIONING` or `TENANT_PROVISIONING_FAILED` detail JSON.

### Tests (`backend/tests/test_provisioning_gate.py`)
- `test_503_during_provisioning` — PASS
- `test_503_on_failed_provisioning` — PASS
- `test_startup_reconciler_cleans_orphans` — PASS

---

## 6. Travel UI — Accounting Mode Toggle

**Before:** `accounting_mode` (`principal` vs `agent`) was hardcoded to `principal` on all bookings.

**After:**
- `BookFromPackageIn` schema has `accounting_mode: AccountingMode = AccountingMode.PRINCIPAL`.
- `create_booking_from_package` persists the value.
- `/dashboard/travel/new` — radio button "Principal / Agent" visible before booking.
- `/dashboard/travel` list table — badge shows Principal or Agent per booking.
- GL books gross revenue + COGS for principal; net commission only for agent.

---

## 7. Third-Party Integration Status

### Customer Portal OTP Login

| Step | Status |
|------|--------|
| `POST /portal/auth/login` — OTP generated & stored in Redis | ✅ Implemented & tested |
| OTP delivered via WhatsApp template `portal_otp_code` | ✅ (falls back to email) |
| `POST /portal/auth/login/verify` — wrong OTP → 401 | ✅ Tested |
| `POST /portal/auth/login/verify` — correct OTP → JWT | ✅ Tested |
| `GET /portal/invoices` with portal JWT → posted invoices only | ✅ Tested |
| `POST /portal/invoices/{id}/pay` → 501 (online payment disabled) | ✅ Intentional |

### Shipping (Bosta / Mylerz)

| Item | Status |
|------|--------|
| Carrier account CRUD (`/api/v1/logistics/carriers`) | ✅ Implemented |
| Available carriers list including `bosta` | ✅ Tested |
| Shipment creation from invoice | 🔶 Requires live Bosta sandbox API key in env |
| Webhook ingestion (`/logistics/webhook/{carrier}`) | ✅ Implemented & tested (signature verified) |
| COD settlement matching (`/dashboard/settlements`) | ✅ UI + reconciliation endpoint implemented |
| GL: cash-with-carrier → cash on settlement | ✅ Implemented in `finance/services/settlement.py` |

### ETA E-Invoicing (Egypt)

| Item | Status |
|------|--------|
| `PUT /api/v1/eta/config` — tenant config | ✅ Implemented & tested |
| `POST /api/v1/eta/egs-codes` — EGS registry | ✅ Implemented & tested |
| Submit invoice to ETA preprod | 🔶 Requires `ETA_CLIENT_ID` + `ETA_CLIENT_SECRET` env vars |
| Accept/reject callbacks | ✅ Webhook handler implemented (`/eta/callbacks`) |

### WhatsApp Plugin

| Item | Status |
|------|--------|
| Invoice notification via WhatsApp template | ✅ Implemented (`notify_contact`) |
| AI-assistant inbound message handling | 🔶 Requires `WHATSAPP_VERIFY_TOKEN` + `WHATSAPP_ACCESS_TOKEN` |

---

## 8. Known Remaining Issues

### Minor test warnings (non-blocking)

- Some tests in `trust/test_trust_network.py` and `test_accounting.py` carry `@pytest.mark.asyncio` on synchronous functions — harmless but noisy. Can be cleaned in a future pass.
- Pydantic V2 `class Config` deprecation warnings in several travel/recruitment models — cosmetic, no behaviour change.
- `ORJSONResponse` deprecation in FastAPI 0.115+ — will auto-resolve when upgraded.

### Third-party credentials needed for full E2E

The following env vars must be set in `.env` for live third-party flows to activate:

```
# Bosta shipping
BOSTA_API_KEY=...

# ETA e-invoicing (preprod)
ETA_CLIENT_ID=...
ETA_CLIENT_SECRET=...

# WhatsApp Business API
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
```

---

## 9. Git History (this round)

```
66b25f80  test: add portal OTP, ETA e-invoicing and logistics carrier tests; wire FakeRedis in conftest
e4a03d13  feat(travel): expose accounting_mode in package booking and travel UI
159fa25b  docs(security): document token security architecture and BFF migration plan
55c19df6  feat(provisioning): template-schema cloning cuts DDL time from ~240s to ~7s; add reconciler tests
b74f1138  feat(rbac): gate 21 routers with RequireRoleForWrites; add POST /auth/users; 175 tests pass
8a0b677e  chore: delete test tenant ui.test.round7@example.com and its schema
```

---

## 10. Checklist

| Task | Status |
|------|--------|
| `pytest -q` — 181/181 passed | ✅ |
| `npm run build` — 42 routes, 0 errors | ✅ |
| `npm run lint` — 0 errors | ✅ |
| Test tenant cleanup (`ui.test.round7`) | ✅ |
| Role gates on all 21 routers | ✅ |
| `POST /auth/users` for non-owner user creation | ✅ |
| Auth security architecture documented | ✅ |
| Provisioning < 30s (achieved ~7s) | ✅ |
| 503 gate + startup reconciler with tests | ✅ |
| Travel accounting mode toggle | ✅ |
| Portal OTP flow with tests | ✅ |
| ETA e-invoicing config with tests | ✅ |
| Shipping carrier setup with tests | ✅ |
| Push to `origin/security-hardening` | 🔄 (next step) |
