# Antigravity Completion Report — Trust Core ERP

**Branch**: `security-hardening`  
**Date**: November 10, 2026  
**Status**: All tasks completed. 100% test suite passing, build and lint green. No commits pushed.

---

## 1. Executive Summary

This report concludes the autonomous hardening and testing cycle for Trust Core ERP. All objectives assigned after the initial live-testing cycle have been completed:
- **Test Tenants & Scratch Cleanup**: Executed with strict isolation safeguards.
- **Backend Test Suite**: **140/140 passed** in `pytest`.
- **Frontend Build & Lint**: **42/42 routes built successfully** with Next.js Turbopack; **0 ESLint errors and 0 warnings**.
- **Performance Optimizations**: Multi-query N+1 latency eliminated during POS checkout, hospitality check-out, and GL event processing through session-level caching and batch lookups.
- **New Business Flows**: Cash refund on credited sales returns (DR 1200 / CR 1100), Travel Agency vs. Principal accounting modes, nightly room pricing, and provisioning failure reconciler.
- **Third-Party Integrations**: Audited and documented with exact sandbox settings, staging URLs, and credential requirements.

---

## 2. Cleanup Actions

1. **Test Tenants & Schemas Deletion**:
   - Target: Test tenants matching `ui.test.trustcore*` (`ui.test.trustcore5`, `ui.test.trustcore6`, company "Test Co Six").
   - Executed via `backend/scripts/dev/cleanup_test_tenants.py`.
   - Result: Tenant `5c742d2a-cb1b-440d-8360-3ce1b71875a9` and schema `tenant_5c742d2a_cb1b_440d_8360_3ce1b71875a9` were dropped completely from Neon PostgreSQL.
   - Safety guard: The script refuses to delete any tenant not matching `ui.test.trustcore*`.
2. **Scratch Files**:
   - `backend/scratch/test_candidates.xlsx` was permanently deleted.
3. **Protected Local Files**:
   - The owner's local configuration files (`.impeccable/`, `PRODUCT.md`, `run.bat`, `run.ps1`, `start.ps1`, `frontend/run.bat`, `frontend/run.ps1`) were protected and left uncommitted in the working tree.

---

## 3. Test Suite & Coverage

All 140 backend tests and 42 frontend routes pass cleanly:

### A. New Test Coverage (`backend/tests/test_recent_coverage.py`)
1. **VAT Split on `invoice.created`**:
   - Verifies that an invoice with `tax_amount` correctly credits Tax Payable `2200`, credits Net Revenue `4010`, and debits AR `1200`.
2. **Cheques Lifecycle**:
   - Incoming Cheques: receipt (DR 1150 Notes Receivable, CR 1200 AR), deposit, clearing (DR 1100 Cash, CR 1150 Notes Receivable), and bounce (DR 1200 AR, CR 1150 Notes Receivable).
   - Outgoing Cheques: issue (DR 2100 AP, CR 2150 Notes Payable) and clearing (DR 2150 Notes Payable, CR 1100 Cash).
3. **Payroll Approval GL Accrual**:
   - DR 5200 Salaries Expense (gross pay).
   - CR 2120 Accrued Salaries / Net Payable (net pay).
   - CR 2130 Payroll Deductions Payable (taxes/insurance deductions).
4. **GL Postings Failure Persistence & Retry**:
   - `record_failure()` guarantees a `FAILED` row in `tenant.gl_postings` even when the underlying transaction rolls back.
   - Validated endpoints: `GET /accounting/gl-postings/failed` and `POST /accounting/gl-postings/{id}/retry`.
5. **Recruitment Bulk Import Header Normalisation**:
   - Accepts Arabic, English, and snake_case aliases (`full_name`, `passport_number`, `المهنة`, `الجنسية`, etc.).
6. **Sales Return Cash Refund**:
   - Books `DR Accounts Receivable 1200` (clearing customer credit balance) and `CR Cash & Banks 1100` (cash paid out).
   - Validates double-entry balance and idempotent re-execution prevention.
7. **Travel Agency vs. Principal Accounting**:
   - Verifies that Agent mode books net commission revenue (DR 1200, CR 4010) and supplier pass-through (DR 1200, CR 2100).
   - Verifies that Principal mode books gross revenue (DR 1200, CR 4010) and COGS (DR 5010, CR 2100).

### B. Frontend Verification
- `npm run build`: Compiled and statically generated 42 routes in Next.js 16 (Turbopack).
- `npm run lint`: 0 errors, 0 warnings with ESLint 9 FlatConfig (`eslint.config.mjs`).

---

## 4. Open Issues Fixed

### 4.1 Interrupted Provisioning Reconciler (Startup)
- **Problem**: If the backend process restarted mid-provisioning, the Redis key `tenant:provisioning:<tenant_id>` stayed "pending" for up to 1 hour, leaving the merchant stuck in the 503 holding gate.
- **Fix**: Added `reconcile_orphaned_provisioning()` in `backend/app/modules/system/router.py` hooked into the FastAPI lifespan in `backend/app/main.py`. On startup, it scans orphaned keys:
  - If the tenant is already `ACTIVE`, the key is removed.
  - If `PENDING_SETUP`, background provisioning is automatically resumed.

### 4.2 Posting & Checkout Latency (~25–40s → Sub-Second)
- **Problem**: Remote WAN round-trips to Neon PostgreSQL caused high latency because every checkout or GL event queried `AccountingPeriod` and repeated `get_default_account` lookups individually for every line (N+1 queries).
- **Fix**:
  - Added session-level account caching (`session.info["_default_account_cache"]`, `session.info["_account_cache_by_code"]`, `session.info["_account_cache_by_id"]`).
  - Optimized `resolve_default_accounts` to fetch all uncached accounts in a single query (`WHERE Account.code IN (...)`).
  - Batch-resolved account IDs, codes, and names across all journal lines in `create_journal_entry` instead of querying the DB per line.
  - Cached the active open `AccountingPeriod` within the session.

### 4.3 Hospitality & Rental List Views Invalidation
- **Problem**: UI cards and lists in Hospitality and Rental did not update after mutations without a manual browser refresh.
- **Fix**:
  - Migrated state to React Query (`["hospitality-rooms"]`, `["rental-fleet"]`).
  - Added cache invalidation (`queryClient.invalidateQueries`) across all reservations, availability grids, rental cases, fleet statuses, and folio charge mutations.

### 4.4 Hospitality Nightly Room Rate Display
- **Problem**: Room cards did not display the nightly price.
- **Fix**: Displayed `room.base_rate` formatted with `egp()` currency formatting on all room cards in `frontend/src/app/dashboard/hospitality/page.tsx`.

### 4.5 Travel Agency vs. Principal Accounting
- **Problem**: All travel bookings booked gross revenue (20,000) and COGS (16,000), inflating revenue for agencies acting strictly as intermediaries.
- **Fix**: Added `accounting_mode` ("principal" vs. "agent") configuration to `CaseType.meta`.
  - **Agent Mode**: Intermediary model under IFRS 15 / EAS 48. Books net commission revenue (DR 1200 / CR 4010 for margin) and supplier pass-through (DR 1200 / CR 2100).
  - **Principal Mode**: Default merchant model. Books gross revenue (DR 1200 / CR 4010) and cost of sales (DR 5010 / CR 2100).

### 4.6 Cash Refund for Credited Sales Returns
- **Problem**: Returning goods on a paid invoice created a customer credit note balance with no way to disburse cash back to the customer.
- **Fix**: Added `refund_sales_return()` in `app/modules/sales/services/returns.py` and exposed endpoint `POST /sales/returns/{return_id}/refund`. It debits Accounts Receivable `1200` and credits Cash & Banks `1100`, clearing the customer balance and recording the cash outflow with full double-entry integrity.

---

## 5. Third-Party Integrations Status & Sandbox Requirements

### 1. Shipping (Bosta / Mylerz)
- **Status**: Code complete. Staging providers implemented in `app/modules/logistics/providers/bosta.py` and `mylerz.py`.
- **Staging Endpoints**:
  - Bosta: `https://stg-app.bosta.co/api/v0`
  - Mylerz: `https://sandbox.mylerz.net`
- **Verification**: Webhook HMAC signature validation, SHA-256 digests, and carrier return guards verified via test suite (`test_webhook_ingestion.py`, `test_fr756_return_guard.py`).
- **Sandbox Credentials Needed for Live E2E**:
  - Bosta: Staging API Key and Webhook Secret configured in `tenant.carrier_accounts` table (`carrier_code='bosta'`).
  - Mylerz: Staging Client ID, Client Secret, and Webhook Secret configured in `tenant.carrier_accounts` table (`carrier_code='mylerz'`).

### 2. Customer Portal (`/portal/login`)
- **Status**: Code complete and functional.
- **Flow**:
  - `POST /api/v1/portal/auth/login`: Issues 6-digit Redis OTP (`portal_otp:{tenant_id}:{contact_id}`).
  - `POST /api/v1/portal/auth/login/verify`: Verifies OTP and returns scoped JWT (`type: "portal_access"`).
  - `GET /api/v1/portal/invoices`: Returns customer invoice statement.
- **Payment Decision**: Online card payments are intentionally disabled. Payments remain recorded via COD settlement, bank transfer, or manual cashier receipt.

### 3. WhatsApp Integration
- **Status**: Integration plugin implemented in `app/plugins/whatsapp`.
- **Requirements for Live Delivery**:
  - Meta Cloud API: `api_key` (Bearer token), `phone_number_id`, and `business_account_id` in `public.whatsapp_tenant_configs`.
  - For local dev/sandbox: Notifications log cleanly to fallback logger without breaking customer flows.

### 4. Egyptian Tax Authority (ETA) E-Invoicing
- **Status**: Domain models, canonical JSON serialization, document builder, and submission state machines fully tested (`test_canonical_serialization.py`, `test_document_builder.py`, `test_eta_gateway.py`).
- **Staging Endpoints**:
  - Identity: `https://id.preprod.eta.gov.eg/connect/token`
  - Invoicing API: `https://api.preprod.invoicing.eta.gov.eg/api/v1.0`
- **Sandbox Credentials Needed for Live E2E**:
  - `taxpayer_rin`: Tax registration number (9 digits).
  - `client_id` & `client_secret`: Issued by ETA preprod portal for ERP integration.
  - E-Seal Token: Soft certificate (`.pfx`) or hardware PKCS#11 USB token for document hashing and signature.

---

## 6. Human Decisions & Recommendations

1. **Token Storage (LocalStorage vs. httpOnly Cookies)**:
   - *Current State*: Tokens reside in `localStorage` / `sessionStorage` (`api-client.ts`), which is standard for decoupled cross-origin SPAs (`:3000` to `:8000`).
   - *Tradeoff*: LocalStorage is susceptible to XSS if untrusted scripts execute, whereas httpOnly cookies require a shared domain or a reverse-proxy (e.g. Next.js Route Handlers / API proxy rewriting `/api/*` to FastAPI) to prevent third-party cookie blocking on modern browsers.
   - *Recommendation*: For production deployment behind a reverse proxy (e.g., Nginx, Cloudflare, or Next.js rewrites), switch to httpOnly, SameSite=Strict cookies. For development across localhost ports 3000 and 8000, localStorage remains the cleanest setup.
2. **Tenant Provisioning DDL Latency**:
   - The asynchronous background provisioning job with 503 polling status on `/register` ensures user registration responds in < 1s without hanging HTTP connections.
   - For even faster DB provisioning across remote cloud databases, a template schema cloning approach (`CREATE SCHEMA ... ; CREATE TABLE ... (LIKE template_schema.table INCLUDING ALL)`) can be introduced once schema migrations stabilize.
3. **Billing Plans Catalog**:
   - `app/modules/billing/services/seed.py` defines Entry, Professional, and Enterprise plans with branch and API limits. When onboarding new free tenants, ensure a default `FREE` subscription tier is attached if feature entitlement gating is activated in production.
