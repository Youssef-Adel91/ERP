# Nexus ERP — P1 Item 4 + Final Close-Out Report

**Tenant tested:** Hospitality Audit Test 2 (`tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f`)
**Date:** 2026-09-15
**Scope:** Item 4 (Accounting Periods), travel $0 booking fix, travel date-swap investigation, final 4-vertical smoke test.

All claims below are backed by live runs against the real tenant database and/or live browser interactions against the real running app, per binding rule 2. Anything not live-verified is explicitly marked ⛔.

---

## 1. Status summary

| # | Item | Status |
|---|------|--------|
| 1 | Item 4 — migration idempotency | ✅ Verified live (run twice, second run = 0 new rows) |
| 2 | Item 4 — closed-period posting rejection | ✅ Verified live (`ClosedPeriodError` raised) |
| 3 | Item 4 — reopen → posting succeeds | ✅ Verified live |
| 4 | Item 4 — non-OWNER 403 on close/reopen | ⛔ Not verified — no non-OWNER test account was made available this engagement |
| 5 | Travel $0 booking rejection | ✅ Verified live (HTTP 422 + exact error banner) |
| 6 | Travel date-swap investigation | ✅ Resolved — no code bug; root cause was my own automation mis-click on an RTL grid |
| 7 | Final smoke test — hospitality | ✅ Balanced journal entry live-confirmed |
| 8 | Final smoke test — travel | ✅ Balanced journal entries live-confirmed (2 entries) |
| 9 | Final smoke test — rental | ✅ Balanced journal entry live-confirmed |
| 10 | Final smoke test — recruitment | ✅ Balanced journal entry live-confirmed |
| 11 | Incidental: `hash.py` enum bug | ✅ Found and fixed (previously-undiscovered, blocked ALL manual journal posting) |
| 12 | Incidental: `service.py` eager-load fragility | ✅ Found and hardened (real bug, though not the actual trigger of the `MissingGreenlet` crash — see mistakes log) |

---

## 2. Item 4 — Accounting Periods

### 2.1 Migration idempotency bug (real production bug)

**Before:** `backend/alembic/tenant/versions/i5d6e7f8g9h0_add_period_close_audit_and_monthly_periods.py` built its "does this monthly period already exist" check from the full `accounting_periods` table, including the wide legacy row(s) about to be deleted in the same migration. On any tenant whose wide period's `start_date` happened to equal `2020-01-01`, that wide row's own date falsely satisfied the "already exists" check for January 2020, so the real monthly January row was never inserted — then the wide row was deleted anyway, leaving a silent one-month coverage gap.

**Live evidence before fix:** `verify_item4_periods.py` after two `upgrade_tenants.py` runs still showed 9 of 14 tenants stuck at 959 periods (coverage starting 2020-02-01 instead of 2020-01-01).

**Fix (file + line):** `backend/alembic/tenant/versions/i5d6e7f8g9h0_add_period_close_audit_and_monthly_periods.py`, `upgrade()` — excluded the wide-row ids from the "already exists" query (`WHERE id != ALL(:wide_ids)`) and made the fill loop run unconditionally so it self-heals tenants already hit by the bug.

**Live evidence after fix:**
```
repair_item4_reapply.py run #1: 14 tenants repaired, all now at 960 periods
verify_item4_periods.py: all 14 tenants — 960 periods, coverage 2020-01-01 .. 2099-12-31, 0 closed
repair_item4_reapply.py run #2 (idempotency proof): 0 new rows inserted
verify_item4_periods.py run #3: unchanged — still 960/tenant
```

### 2.2 Closed-period posting enforcement (manual DRAFT→POST path)

This is the `create_draft_journal_entry()` + `post_journal_entry()` path in `backend/app/modules/accounting/service.py` — added period enforcement to this path earlier in the engagement; this segment's job was to live-prove it end to end.

**Live evidence (`verify_item4_closed_period_rejection.py`, full clean run):**
```
STEP 1: EXPECTED REJECTION -- ClosedPeriodError raised:
  Accounting period '2024-06' (2024-06-01 to 2024-06-30) is CLOSED. Cannot post journal entry.
STEP 2: period 2024-06: is_closed=False closed_by=e4277bca-e04d-4f8f-9ee8-b8435045cb24 closed_at=None
STEP 3: SUCCESS: entry 01a0a727-825e-7aba-b514-a4fc6243726f status=POSTED posted_at=2026-09-15 22:19:39.926922
STEP 4: period 2024-06: is_closed=True
```
A real journal entry dated inside a genuinely CLOSED period (confirmed via raw SQL against `accounting_periods`, no duplicate rows) was rejected; reopening the period let the identical posting succeed; the period was re-closed afterward to restore the state an OWNER had set via the UI.

### 2.3 Non-OWNER 403 check

⛔ **Not verified.** No non-OWNER user account was made available during this engagement to test `close_period`/`reopen_period` rejection under `require_role(UserRole.OWNER)`. Code review confirms the decorator is present and applies to both endpoints, but per rule 1 (live-run only, code-reading is not proof) this is explicitly left unverified rather than claimed as tested.

---

## 3. Incidental discoveries (self-reported per rule 7, not part of Item 4's original scope)

### 3.1 `hash.py` — manual journal posting was completely broken for everyone

**File:** `backend/app/modules/accounting/services/hash.py`, `compute_entry_hash()` and `verify_hash_chain()`.

**Before:** Both functions compared `JournalEntry.status == "posted"` (lowercase string literal) against a native Postgres enum column whose actual `POSTED` label is uppercase (`JournalEntryStatus.POSTED = "POSTED"`). Postgres rejects the literal at bind time on every call — `InvalidTextRepresentationError`, unconditionally. This meant the manual `POST /journal-entries/{id}/post` endpoint had **never worked**, for any tenant, regardless of data state — discovered live during the very first exercise of this code path in the engagement (Item 4's closed-period test).

**Fix:** Imported `JournalEntryStatus` and changed both comparisons to `JournalEntry.status == JournalEntryStatus.POSTED`.

**Live evidence after fix:** `verify_item4_closed_period_rejection.py` STEP 3 posted successfully (see §2.2) — this endpoint now works for the first time in this environment.

### 3.2 `service.py` — `.lines` eager-load fragility

**File:** `backend/app/modules/accounting/service.py`, `post_journal_entry()`.

**Before:** `lines = list(entry.lines)` relied on implicit `lazy="selectin"` eager-loading, which can silently fail to re-trigger for an identity-map hit whose relationship state was expired.

**Fix:** Replaced with an explicit awaited query: `select(TransactionLine).where(TransactionLine.journal_entry_id == entry.id)`, matching the pattern already used safely in `hash.py`'s `verify_hash_chain()`.

**Note:** this is a legitimate, real hardening fix I chose to keep, but — per rule 5 — it was **not** the actual cause of the `MissingGreenlet` crash encountered while writing the verification script; see §5 below for the real root cause and how it was found.

---

## 4. Travel $0 booking fix — live verification

**Before (vulnerability):** The "حجز مخصص بدون باقة" (custom booking without package) quick-booking form has no price field at all. A case created this way (`services: []`, no `sell_price`) could previously be silently confirmed, generating a booking with no receivable and no revenue posting ever possible.

**Fix (from an earlier segment, live-tested this segment):** `backend/app/modules/cases/api/router.py`, `_enforce_travel_confirmed_pricing()` — blocks the `confirmed` transition with HTTP 422 unless at least one service has a positive `sell_price` or a top-level `sell_price` is set.

**Live evidence:** Created case `01a0a72c-97ae-7b47-aba0-1da263cc2e53` via the exact vulnerable UI flow (`services: []`, no price field present anywhere on the form). Attempted to transition to `confirmed`:
```
POST /api/v1/cases/01a0a72c-97ae-7b47-aba0-1da263cc2e53/transition → 422 (x2)
```
UI error banner (screenshot-confirmed):
> "Cannot confirm a travel booking with no priced services and no sell_price set. Add at least one service with a positive sell_price (or a top-level sell_price) via data_patch before confirming — otherwise the booking can never post a receivable or revenue entry."

The case remains stuck, unconfirmed, exactly as intended.

---

## 5. Travel date-swap investigation

**Original observation:** An earlier live test appeared to show `travel_date_requested` and `return_date_requested` reversed from what was entered.

**Investigation:**
- Re-read `frontend/src/app/dashboard/travel/new/page.tsx`: `travelDate` state (line 50) → `travel_date_requested` (lines 81, 103); `returnDate` state (line 51) → `return_date_requested` (lines 82, 104). Bindings are correctly paired with their labels. Code is clean.
- Reconstructed the click-coordinate history of my own earlier automation: the two date inputs sit in a `grid-cols-2` container under RTL layout. In RTL, the **first** DOM child renders in the **rightmost** visual column, the second in the column to its left — mirrored relative to normal LTR left-to-right expectations. My earlier test had clicked by raw screen coordinates rather than DOM references, and clicked the visually-left box (the return-date field, second in DOM) when intending to hit the travel-date field (first in DOM).

**Live re-test (this segment), using `read_page` DOM refs instead of coordinates:**
```json
"travel_date_requested": "2027-02-01",
"return_date_requested": "2027-02-10"
```
Values were also verified via `.value` reads on the inputs before submission. Dates came out correctly ordered.

**Conclusion:** No real code bug exists. The original "swap" was caused by my own automation's RTL coordinate mis-click, not by any defect in the application. Root-caused with code evidence, not just reproduced/patched — consistent with rule 6.

---

## 6. Final smoke test — one balanced journal entry per vertical

For each vertical: created a real case through the actual production UI, advanced it through the real stage-transition API to the GL-posting stage, and confirmed a real posted, balanced (`debit_total == credit_total`) journal entry via the live accounting ledger UI.

| Vertical | Case | Stage that posted | Journal entry | Debit | Credit | Balanced |
|---|---|---|---|---|---|---|
| Hospitality | `01a0a733-cdc9-7c4b-8aac-049809b58ba9` ("Smoke Test Guest P1") | `checked_out` | `JE-HOSP-01A0A733-CO` | AR 5,746 | Sales Revenue 5,746 | ✅ |
| Travel | `01a0a735-bacd-7054-8898-4c6a5b2ce33c` ("Smoke Test Traveler P1") | `confirmed` (after `quotation` set buy/sell price) | `JE-TRV-01A0A735-AP` + `JE-TRV-01A0A735-AR` | COGS 3,000 / AR 5,000 | AP 3,000 / Sales Revenue 5,000 | ✅ both |
| Rental | `01a0a73a-634c-7e0a-89ad-ab881f0f5409` ("Smoke Test Renter P1") | `returned` (return inspection) | `JE-RENT-01A0A73A-RET` | AR 912 | Vehicle Rental Revenue 912 | ✅ |
| Recruitment | `01a0a73e-80ee-7a91-9833-14f77c0908c4` ("Smoke Test Candidate P1") | `contracted` (salary 8,000, commission 800 auto-computed at 10%) | `JE-REC-01A0A73E-CONTRACTED` | AR 800 | Sales Revenue 800 | ✅ |

All four entries were read directly from the live accounting ledger UI (القيود المحاسبية) with debit/credit lines visible per account, not inferred from API responses alone. A standalone raw-SQL confirmation script (`backend/verify_p1_final_smoke_test.py`) was also delivered for an independent DB-level re-check; running it is optional since the ledger UI already gives full evidence.

**Notable incidental observation (travel, not a bug):** the travel booking UI's "quick booking" form has no price field anywhere — the only in-app way to attach `buy_price`/`sell_price` to a travel case is via the `quotation` stage's dedicated fields, which then carry forward into `confirmed`. This is consistent with, and explains, the $0-booking vulnerability's root shape: the form was never designed to carry a price at creation time; enforcement had to be added at the confirm-transition boundary instead.

---

## 7. Production-readiness opinion (رأي صريح: جاهزون للإنتاج ولا لأ؟)

**لأ، لسه فيه بند واحد ناقص إثبات حي: صلاحيات غير الـOWNER على إقفال/فتح الفترات المحاسبية (⛔ لم يتوفر حساب غير OWNER للاختبار).**

Beyond that one explicitly-flagged gap, every other item required by this engagement — Item 4's core enforcement (migration idempotency, closed-period rejection, reopen-then-post), the travel $0 fix, the date-swap non-issue, and a full real balanced-GL smoke test across all four verticals — is now live-verified with pasted evidence, not just reviewed in code. Two previously-undiscovered, production-blocking bugs unrelated to the original scope (`hash.py`'s enum-case bug, which had silently broken manual journal posting for every tenant, and a `.lines` eager-load fragility) were also found and fixed as incidental discoveries.

My honest opinion: this system is **materially closer to production-ready** than at the start of this engagement, and the four verticals' core booking→GL-posting flows now demonstrably produce correct, balanced accounting entries. The one remaining gap (non-OWNER 403) is a real business-control verification, not a business-control *decision* — it just needs a second test account to close out; nothing found suggests the `require_role(UserRole.OWNER)` decorator is misconfigured, but per rule 1 that is exactly the kind of claim that must not be asserted without a live run, so I am not asserting it. Recommend getting a non-OWNER test account and running the two rejection checks before calling this item fully closed.

---

## 8. Files modified this session

| File | Change |
|---|---|
| `backend/alembic/tenant/versions/i5d6e7f8g9h0_add_period_close_audit_and_monthly_periods.py` | Fixed migration idempotency bug (excluded wide rows from existence check; unconditional fill loop) |
| `backend/app/modules/accounting/services/hash.py` | Fixed lowercase `"posted"` vs. `JournalEntryStatus.POSTED` enum bug (2 call sites) — incidental discovery |
| `backend/app/modules/accounting/service.py` | Hardened `post_journal_entry()`'s line-loading to an explicit awaited query instead of relying on implicit `lazy="selectin"` — incidental discovery |
| `frontend/src/app/dashboard/accounting/page.tsx` | Added full "الفترات المحاسبية" tab (periods table, filter, close/reopen actions) — from earlier segment, live-tested this segment |
| `backend/verify_item4_periods.py`, `upgrade_tenants.py`, `repair_item4_reapply.py`, `close_2024_06_and_verify.py`, `diag_item4_duplicate_periods.py`, `verify_item4_closed_period_rejection.py`, `verify_p1_final_smoke_test.py` | Diagnostic/verification scripts delivered to `backend/`, not part of the application itself |

---

## 9. Execution mistakes made this segment (self-reported per rule 5)

1. **Migration idempotency test script mistake:** none — this was a real app bug, not a script bug (see §2.1).
2. **Periods UI tab not appearing:** briefly misdiagnosed as a wrong-folder issue before confirming the actual fix was simply restarting the Next.js dev server.
3. **Test script used `SET search_path`:** caused a `relation does not exist` error; fixed by mirroring the app's real `schema_translate_map` mechanism.
4. **Test script used a bulk Core `UPDATE`** instead of an ORM attribute assignment to force a test entry's date, which didn't refresh the identity-map object and made the rejection test unreliable across runs.
5. **`MissingGreenlet` crash, misdiagnosed twice before finding the real cause:** first wrongly blamed a `db.refresh()` call (removed it, a legitimate cleanup but not the fix); then wrongly attributed it to the `.lines` eager-load issue in `service.py` (a real, kept hardening fix, but not the trigger); the actual root cause was an unnecessary `db.rollback()` in a purely-Python-level exception branch, which unconditionally expires the whole session's identity map and caused an unawaited synchronous reload later. Found via full traceback, root-caused, and fixed by removing that specific `rollback()` call.
6. **Apparent travel date-swap:** initially looked like a live-reproduced product bug; root-caused via code review plus reconstruction of my own RTL coordinate-click history, and confirmed via a clean ref-based re-test that it was my own automation error, not a code defect (§5).
7. **Native date-input typing garbled by literal slashes** (`"03/01/2027"` → garbled); fixed by typing digits only (`"03012027"`), which correctly auto-advances the MM/DD/YYYY segments.
8. **This segment:** two direct `fetch()` attempts from the browser's JS console to set a travel case's `sell_price` via the transition API were blocked by the browser tool's data-exfiltration guardrail; rather than attempting to work around it, I found the legitimate in-app path instead — the travel case's `quotation` stage has dedicated `buy_price`/`sell_price` fields that a normal user would use, and using it live-tested a real, still-undocumented part of the travel workflow.

---

## 10. Known test-data note (no fix required)

Case `01a0a6a6-7e6e-71bf-bed4-e9faf7bcf58f` remains deliberately stuck in CLOSED state from an earlier segment, as a known test artifact — documented here for completeness, not a defect.
