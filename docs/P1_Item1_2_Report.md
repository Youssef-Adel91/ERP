# تقرير P1 — البند 1 (Idempotency Diagnosis) والبند 2 (gl_postings Guard)

**تاريخ التنفيذ:** 15 سبتمبر 2026
**التينانت المستخدم في كل الأدلة:** `tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f` (Hospitality Audit Test 2)
**قاعدة العمل:** كل نتيجة هنا إما دليل حي (استعلام SQL فعلي عبر سكريبت شغّله المستخدم، أو استدعاء API حي عبر المتصفح) أو مُعلَّم صراحة ⛔ لو لسه معتمد على قراءة الكود بس.

---

## ملخص سريع

| البند | الحالة |
|---|---|
| بند 1 — تشخيص عدم التكرار | ✅ اتبلغ واتوافق عليه قبل كده |
| بند 2 — شرط 1: الجدول في سكيما التينانت | ✅ مُثبت حيًا |
| بند 2 — شرط 2: skip-as-success (مش crash) | ✅ مُثبت حيًا |
| بند 2 — شرط 3: reserve-before-post في نفس المعاملة | ⛔ مُثبت من الكود فقط، مش من محاكاة كراش حية |
| بند 2 — شرط 4: entry_kind لإعادة الترحيل | ✅ موثّق، ومتسق مع البيانات الحية |
| تقرير التكرارات قبل تفعيل القيد | ✅ مُثبت حيًا (DUP-TEST-001 اتمسكت) |
| Backfill البيانات القديمة لـ gl_postings | ✅ مُثبت حيًا (10 صف) |
| نقل الفلاجات القديمة لـ `_legacy_gl` | ✅ مُثبت حيًا (12 حالة، ومثال حجز 14 سبتمبر) |
| تنظيف DUP-TEST-001 | ⛔ لسه معلّق — قرار محتاج موافقتك (شرحه تحت) |
| بند 5 — تدقيق localStorage | ✅ اتقفل، مفيش تصعيد P0 |
| باگ جانبي اتكتشف: `/forgot-password` و`/reset-password` بيرجعوا 401 دايمًا | ✅ مُثبت حيًا، غير مُصلَّح لسه |

---

## 1) بند 1 — التشخيص (تذكير)

السبب الحقيقي لعدم حصول تكرار في مسار الـ case transitions هو قفل `with_for_update()` على صف الـ Case داخل `transition_case()` — مش أي ضمانة على مستوى الليدجر نفسه. اتثبت ده حيًا بعمل نفس الطلب 5 مرات بالتوازي على نفس الحالة (طلعت النتيجة الصحيحة بالظبط)، مقابل قدرة الليدجر نفسه على قبول نفس المرجع مرتين (`DUP-TEST-001`، اتنين 201). ده اتبلغ واتوافق عليه قبل كده، وهو الأساس اللي بُني عليه بند 2.

---

## 2) بند 2 — نظام `gl_postings`

### الملفات

| الملف | التغيير |
|---|---|
| `app/modules/accounting/models/posting.py` | جديد — موديل `GLPosting` + enum الحالة، بقيد `UNIQUE(source_type, source_id, entry_kind)` |
| `app/modules/accounting/services/gl_posting.py` | جديد — `reserve_posting()` / `mark_posted()` / `mark_failed()` / `get_posting_status()` |
| `app/core/events/invoice_payload.py` | إضافة `source_type`/`source_id`/`entry_type` كحقول إلزامية |
| `app/modules/accounting/events.py` | `handle_invoice_created` بقى يعدي على `reserve_posting()` قبل أي `create_journal_entry` |
| `app/plugins/{hospitality,rental,travel,recruitment}/listeners.py` | إزالة فلاجات `case.data` القديمة، تحويل كل الـ payloads لـ `build_invoice_created_payload()` |
| `alembic/tenant/versions/h4c5d6e7f8g9_add_gl_postings.py` | جديد — الجدول + الـ enum + تقرير التكرارات + backfill + نقل الفلاجات القديمة |

### التحقق الحي — شرط 1: الجدول في سكيما التينانت

```
SELECT n.nspname AS schema_name, c.relname AS table_name
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relname = 'gl_postings'
→ table gl_postings -> schema = tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f

SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conname = 'uq_gl_postings_source_kind'
→ constraint uq_gl_postings_source_kind on tenant_e1ee4d0e_....gl_postings:
  UNIQUE (source_type, source_id, entry_kind)
```

مفيش أي نسخة في `public`. الشرط الأول اتحقق كامل.

### التحقق الحي — شرط 2: skip-as-success

اخترت صف حقيقي موجود بالفعل POSTED (`source_id=01a0a635-a232-7c1f-bb4b-985b0ce9badc`, `entry_kind=hospitality_checkout_revenue`, نفس القيد `JE-HOSP-01A0A635-CO` من تقرير P0)، وشغّلت `reserve_posting()` عليه تاني بنفس القيم — نفس دالة `handle_invoice_created` الحقيقية بتستخدمها:

```sql
INSERT INTO ....gl_postings (...) VALUES (...)
ON CONFLICT ON CONSTRAINT uq_gl_postings_source_kind DO NOTHING
RETURNING ....gl_postings.id
```

النتيجة:
```
reserve_posting() returned: None
row count before retry: 1
row count after retry:  1
```

مفيش استثناء، مفيش 500، والعدد ثابت. الدالة رجّعت `None` وده بالظبط الإشارة اللي الهاندلر الحقيقي بيقرا منها "مفيش حاجة تتعمل". الشرط التاني اتحقق كامل — **لكن لاحظ**: الاختبار ده اتعمل على قيد حقيقي جه من مسار الأحداث (invoice.created)، مش على `DUP-TEST-001` نفسها. التفاصيل والسبب في قسم "تنظيف DUP-TEST-001" تحت.

### شرط 3: reserve-before-post في نفس المعاملة — ⛔ مش مُثبت حيًا بمحاكاة كراش

الكود بيعمل `reserve_posting()` ثم `create_journal_entry()` في نفس الـ session/transaction قبل أي commit (شايفه في `app/modules/accounting/events.py`)، وده متسق مع إن كل الـ 10 صفوف الموجودة فعلاً كلها `POSTED` ومعاها `journal_entry_id` حقيقي (مفيش ولا صف عالق في `RESERVED` من غير قيد). لكن مفيش عندي دليل حي لمحاكاة كراش فعلي في نص المعاملة (زي قطع الاتصال بعد الـ reserve وقبل الـ commit) يثبت إن الـ rollback فعلاً بيمسح الاتنين مع بعض. ده لسه معتمد على قراءة الكود، وهبقى واضح إنه مش مُختبر حي.

### شرط 4: entry_kind لإعادة الترحيل

الـ 10 صفوف الموجودة فعليًا بتستخدم القيم دي بالظبط:
`hospitality_checkout_revenue`, `rental_return_revenue`, `travel_customer_receivable` (×2), `travel_supplier_payable` (×2), `recruitment_commission` — كلها متسقة مع القائمة الموثقة في docstring الموديل. أي تعديل مستقبلي بعد الترحيل هيستخدم `<kind>_reversal` كـ entry_kind مختلف، فمش هيتصادم مع القيد.

---

## 3) الميجريشن `h4c5d6e7f8g9` — نتائج التشغيل الفعلية

```
[gl_postings] DUPLICATE JOURNAL ENTRIES DETECTED in schema tenant_e1ee4d0e_...
  -- same `reference` --
     reference='DUP-TEST-001'  count=2

[gl_postings] ...: backfilled 10 posting row(s) from 10 source-identified journal entr(y/ies);
  0 skipped as duplicates of an existing key.
[gl_postings] ...: moved legacy posting flags on 12 case(s) under '_legacy_gl'.
```

- تقرير التكرار مسك `DUP-TEST-001` بالظبط، وماعملش أي حذف — تقرير فقط.
- الـ backfill طلع 10 صف، وده مطابق تمامًا لعدد صفوف `gl_postings` اللي شفتها فعليًا بعد كده (10) — يعني `DUP-TEST-001` **ماخدتش** صف backfill، وده صح: مرجعها `DUP-TEST-001` مش من أنماط `JE-HOSP-*`/`JE-TRV-*`/إلخ اللي الميجريشن بتعرف تحولها لـ entry_kind، فاتسيبت من غير ربط — بدل ما تتخمّن قيمة غلط.
- 12 حالة اتنقل الفلاج بتاعها.

---

## 4) حالة حجز 14 سبتمبر — دليل القبول المتفق عليه

فتحت الحالة مباشرة من الداشبورد (`/dashboard/cases/01a0a1bc-9436-777a-8252-0f682c95d265`):

```json
{
  "_legacy_gl": {
    "posting_error": "UndefinedTableError: relation \"tenant_e1ee4d0e_....folio_items\" does not exist",
    "posting_failed": true,
    "gl_revenue_posted": true,
    "posting_failed_stage": "checked_out"
  },
  "daily_rate": 1500,
  "folio_total": 6000.96,
  "final_folio_total": 6000.96
}
```

- الفلاجات الأربعة القديمة (`posting_error`, `posting_failed`, `gl_revenue_posted`, `posting_failed_stage`) اتنقلوا تحت `_legacy_gl` وشالهم من أسمائهم الأصلية — أي كود لسه بيقرا `case.data["gl_revenue_posted"]` مباشرة هيرجع `None`/فارغ بدل ما يثق في قيمة قديمة غلط.
- **مفاجأة إيجابية**: السبب الحقيقي التاريخي دلوقتي ظاهر بوضوح — الحجز فشل وقتها لأن `folio_items` مكانش موجود أصلاً (نفس مشكلة P0 الأولى)، مش أي حاجة تانية.
- تأكدت من الـ 13 قيد الموجودين في `journal-entries` إن مفيش أي قيد مرتبط بالحجز ده — يعني الحالة النهائية متّسقة: "فشل حقيقي قديم، معملش ترحيل، ومفيش قيد" بدل التناقض القديم (`gl_revenue_posted: true` + `posting_failed: true` مع بعض).

---

## 5) تنظيف DUP-TEST-001 — قرار محتاج موافقتك

هنا لازم أكون واضح بحاجة مهمة: **`DUP-TEST-001` اتعملت أصلاً من خلال `POST /accounting/journal-entries` اليدوي (إنشاء قيد يدوي DRAFT)، مش من مسار `invoice.created` التلقائي.** يعني هي أصلاً برّه نطاق حماية `gl_postings` بالتصميم — القيد اليدوي معندوش `source_type`/`source_id`/`entry_kind` بيربطه بحدث عمل حقيقي، فمفيش طريقة تقنية يتربط بيها بنظام الحجز الجديد.

عشان كده اختبار "إعادة نفس الترحيل" (شرط 2 فوق) اتعمل على قيد حقيقي جه من `invoice.created` (حجز فندقي فعلي POSTED)، مش على `DUP-TEST-001` نفسها — لأن إعادة إرسال `DUP-TEST-001` عبر `POST /journal-entries` هتنجح تاني وتعمل نسخة تالتة، **مش لأن الإصلاح مش شغال، لكن لأن مسار الإدخال اليدوي للقيود كان دايمًا برّه نطاق P1 بند 2 من الأساس** — ده نفس نوع الملاحظة اللي المفروض أبلغك بيها بدل ما أفترض إنها هتتغطى.

الخيارات قدامك:
1. **اعتبر الاختبار اللي اتعمل على القيد الحقيقي كافي**، واتنظف `DUP-TEST-001` دلوقتي (حذف الصفين DRAFT).
2. **سيب `DUP-TEST-001` لحد ما نضيف حماية منفصلة** على مستوى `reference` للقيود اليدوية كمان (ده هيبقى بند جديد برّه نطاق P1 الحالي، يستاهل نقاش منفصل).
3. **نظفها دلوقتي وبس وثّق في التقرير** إن القيود اليدوية لسه من غير حماية تكرار (حالة معروفة، مش باگ جديد).

قوللي تختار إيه وأنا أنفذ.

---

## 6) بند 5 — تدقيق localStorage (مُقفل، مفيش تصعيد P0)

- `frontend/src/lib/api-client.ts` سطر 63/116: `getTenantId()` بتتستخدم مرة واحدة بس — إعادة حفظ القيمة بعد تجديد التوكن، مش بناء هيدر أو قرار صلاحية. كل تفويض الطلبات جاي من `Authorization: Bearer` فقط، والباك إند بيفك الـ tenant_id من الـ JWT.
- `frontend/src/lib/portal-api-client.ts` + `app/portal/login/page.tsx` سطر 27: `getPortalTenantId()` بتتستخدم بس كقيمة افتراضية في حقل فورم قابل للتعديل، مش بتتبعت تلقائيًا لأي حاجة.
- `backend/app/modules/portal/api/auth.py` سطر 115، 169: حتى الـ tenant_id ده لما بيتبعت في طلب OTP، هو بيتحقق منه Redis-scoped بـ `(tenant_id, contact_id)` معًا — قيمة غلط أو قديمة هتخلي تسجيل الدخول يفشل بس، مش تدّي وصول لتينانت غلط.

**النتيجة: مفيش أي مسار بيستخدم localStorage في قرار صلاحية حي. البند ده مقفول.**

---

## 7) اكتشاف جانبي: `/forgot-password` و`/reset-password` مكسورين تمامًا

أثناء محاولة تسجيل الدخول للتينانت الصح، اكتشفت إن `TenantMiddleware` (`app/core/db/database.py` سطر 882-889) بيحدد `_BYPASS_PATHS` صراحة كـ:
```
/api/v1/auth/login
/api/v1/auth/register
/api/v1/auth/refresh
/api/v1/system/auth/login
/api/v1/system/auth/refresh
/api/v1/system/tenants/register
```

**`/api/v1/auth/forgot-password` و`/api/v1/auth/reset-password` مش موجودين في القائمة**، رغم إن الراوتر نفسه (`app/modules/system/router.py`) بيوثّقهم صراحة كـ "public endpoint — no Bearer token required". جربتها حيًا (POST بدون توكن):

```json
{"status": 401, "body": {"detail": "Authentication required. Provide a Bearer token."}}
```

**الأثر:** أي مستخدم نسي كلمة السر في التطبيق ده **معندوش أي طريقة يستردها بنفسه** — الميدلوير بيرفض الطلب قبل ما يوصل للراوتر خالص، حتى لو الإيميل والفلو صح 100%. ده باگ حي إنتاجي حقيقي، مش نظري.

**الحالة:** ⛔ لسه مش مُصلَّح — اكتشفته أثناء الشغل على بند 1+2، ومحتاج قرارك: أصلحه دلوقتي (إضافة سطرين لـ `_BYPASS_PATHS`) ولا نأجله لبند منفصل؟

---

## 8) أخطاء حصلت أثناء التنفيذ وتصحيحها

1. **تصحيح تقرير P0 سابق**: كنت قلت "الأربع موديولات بقت تستخدم الـ helper" — ده مكانش صح، **السياحة بس** كانت بتستخدمه فعليًا. اتكشفت الغلطة أثناء تحويل الباقي في بند 2، والتلاتة (فنادق/تأجير/توظيف) اتحولوا فعلاً دلوقتي.
2. **سكريبت التحقق الأول (`verify_gl_postings.py` نسخة v1) كان فيه غلطة مني**: استخدمت SQL خام بدون تأهيل سكيما (`FROM gl_postings` بدل `FROM <schema>.gl_postings`)، فوقع بـ `UndefinedTableError` رغم إن الجدول موجود فعلاً وصح. اتصلحت بالتحويل لاستخدام الـ ORM model (`select(GLPosting)`) اللي بيتحول تلقائي لسكيما التينانت. الجزء (A) بتاع نفس السكريبت كان صح من الأول لأنه استخدم pg_catalog مباشرة.
3. **دخلت بالغلط على تينانت تاني** (`5410d254-...`) في منتصف الجلسة، واكتشفت كده إن حساب `abanobelwy86@gmail.com` مش نفس حساب `hospaudit21789412307956@gmail.com` اللي كل الأدلة عليه. اتصلحت بإعادة تعيين الباسورد مباشرة في قاعدة البيانات (سكريبت Python، مش عن طريق psql) بعد ما اكتشفنا إن فلو "نسيت كلمة المرور" نفسه معطوب (انظر بند 7).

---

## الخطوة التالية

مستني منك:
1. قرارك بخصوص تنظيف `DUP-TEST-001` (خيار 1، 2، أو 3 في قسم 5).
2. هل تحب أصلح باگ `_BYPASS_PATHS` (بند 7) دلوقتي ولا أأجله؟

وبعد كده هكمل لبند 3 (إثبات إن الفشل الصامت بقى ظاهر للمستخدم فعليًا، مش بس مسجل في اللوج) زي ما كان متفق.
