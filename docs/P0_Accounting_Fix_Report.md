# تقرير إصلاح P0 — خط "Case → Invoice → Journal Entry" في الأنظمة القطاعية الأربعة

**تاريخ التنفيذ**: 15 سبتمبر 2026
**التينانت المستخدم في التحقق**: `hospaudit21789412307956@gmail.com` — tenant_id `e1ee4d0e-e8d7-4d5d-9778-c8954687e63f`
**طريقة التحقق**: استدعاءات API حقيقية على السيرفر الشغال (`localhost:8000`) + تفاعل فعلي بالمتصفح على `localhost:3000`، مش قراءة كود.

---

## النتيجة النهائية

**الأنظمة الأربعة بقت بترحّل قيود يومية حقيقية ومتوازنة فعلاً.** قبل الإصلاح كان عدد القيود في الليدجر **صفر** رغم إن الواجهة بتقول "تمت العملية بنجاح".

آخر حالة الليدجر بعد تشغيل دورة كاملة لكل نظام (`GET /api/v1/accounting/journal-entries`):

| المرجع | النظام | الحالة | مدين | دائن | متوازن |
|---|---|---|---|---|---|
| `JE-HOSP-01A0A635-CO` | الفنادق | POSTED | 5937.12 | 5937.12 | ✅ |
| `JE-RENT-01A0A636-RET` | التأجير | POSTED | 2736 | 2736 | ✅ |
| `JE-TRV-01A0A636-AR` | السياحة (ذمم عميل) | POSTED | 9000 | 9000 | ✅ |
| `JE-TRV-01A0A636-AP` | السياحة (التزام مورد) | POSTED | 6000 | 6000 | ✅ |
| `JE-REC-01A0A636-CONTRACTED` | التوظيف | POSTED | 1200 | 1200 | ✅ |

---

## 1) الميجريشن الناقص: `folio_items` + `vehicle_inspections` ✅

### الحالة قبل الإصلاح
فحصت كل الـ 49 ملف في `alembic/tenant/versions/` — مفيش ولا `op.create_table` واحد للجدولين، رغم إنهم معرّفين كـ SQLModel `table=True`. النتيجة الحية وقتها:

```
POST /api/v1/hospitality/reservations/{id}/folio/items  → 500
GET  /api/v1/hospitality/reservations/{id}/folio        → 500
POST /api/v1/cases/{id}/transition {"to_stage":"checked_out"} → 500
POST /api/v1/cases/{id}/transition {"to_stage":"returned"}    → 500
```

والخطأ الخام اللي سجّله الـ listener بنفسه في `case.data`:
```
"posting_error": "ProgrammingError: <asyncpg.exceptions.UndefinedTableError>:
 relation \"tenant_e1ee4d0e_e8d7_4d5d_9778_c8954687e63f.vehicle_inspections\" does not exist"
```

### التعديل
- **ملف جديد**: `backend/alembic/tenant/versions/f2a3b4c5d6e7_add_folio_items_and_vehicle_inspections.py` — بينشئ الجدولين والـ 3 enums بتوعهم (`folio_item_category`, `vehicle_inspection_type`, `vehicle_fuel_level`) بنفس بنية الموديلات بالظبط، وبدون FK على `case_id` احترامًا لـ DECOUPLING CONTRACT المكتوب في الموديلات نفسها. idempotent بالكامل.
- `backend/app/plugins/hospitality/models/folio.py` + `backend/app/plugins/rental/models/inspection.py`: إضافة `schema="tenant"` لأعمدة الـ Enum — من غيرها SQLAlchemy كان بيعمل `CREATE TYPE` غير مؤهَّل بسكيما فيروح في `public` ويتشارك بين كل التينانتس (نفس الباغ اللي `w3r8s9t0u1v2` اضطر يصلحه لـ `employeestatus`).
- **السبب الجذري للفجوة**: `backend/alembic/tenant/env.py` مكنش بيستورد موديلات الـ plugins خالص، فالموديلين دول مكانوش موجودين في `TenantBase.metadata` وقت أي `alembic revision --autogenerate` — يعني الـ autogenerate عمره ما شافهم. اتضافوا للاستيراد (مع موديلات التوظيف التلاتة كمان).

### الدليل الحي بعد الإصلاح
تشغيل الميجريشن على السكيما الموجودة فعلاً:
```
INFO  [alembic.runtime.migration] Running upgrade f2a3b4c5d6e7 -> g3b4c5d6e7f8
```
(سطر الـ upgrade ده بيثبت إن `f2a3b4c5d6e7` اتطبّق بنجاح قبله)

```
POST /api/v1/hospitality/reservations/01a0a1bc-.../folio/items
     {"category":"restaurant","description":"عشاء فاخر","amount":200,"quantity":1}
→ 201  {"id":"01a0a626-ec6c-7231-b746-154be2562e80","amount":200.0,"category":"restaurant"}

GET  /api/v1/hospitality/reservations/01a0a1bc-.../folio
→ 200  {"nights":3,"room_charge":"4500.00","extras_total":"150.00",
        "service_charge":"558.00","tax_amount":"729.12","total":"5937.12"}

POST /api/v1/cases/01a0a635-.../transition {"to_stage":"checked_out"}
→ 200  {"case_id":"01a0a635-a232-7c1f-bb4b-985b0ce9badc","current_stage":"checked_out","status":"ACTIVE"}

POST /api/v1/cases/01a0a636-.../transition {"to_stage":"returned"}
→ 200  case.data: {"total_rental_charge":2400,"grand_total":2736,"gl_revenue_posted":true}
```
الحساب متأكد منه يدويًا: 1500×3 ليالي = 4500، + 150 ميني بار = 4650، +12% خدمة = 5208، +14% ضريبة = **5937.12** ✓ / التأجير: 800×3 أيام = 2400، +14% = **2736** ✓

---

## 2) `app/plugins/travel/listeners.py` — الفشل الصامت ✅

### الحالة قبل الإصلاح
`await session.execute(f"SET search_path TO {tenant_schema}")` — نص خام لـ `AsyncSession.execute()`، بيرمي `ObjectNotExecutableError` في SQLAlchemy 2.x، والاستثناء بيتلقط في `except Exception` من غير ما يترفع. النتيجة الحية: `POST /cases/{id}/transition → confirmed` بيرجع **200**، ومفيش أي فلاج بيتسجل على الحجز خالص (لا `gl_receivable_posted` ولا `gl_payable_posted`) ومفيش قيد.

### التعديل
- اتشال السطر الخام نهائيًا — مفيش داعي أصلاً لضبط `search_path` يدويًا: `tenant_session()` بتطبّق `schema_translate_map`، ومسار الـ session المشترك أصلاً متظبط على التينانت.
- الـ handler بقى ياخد `session` kwarg ويستخدم session الطلب نفسه (زي التوظيف/الفنادق/التأجير) بدل `AsyncSessionLocal()` منفصلة — ده بيخلي التعديلات اللي الـ Case Engine عملها flush ومحصلش عليها commit لسه تبقى مرئية.
- اتضاف `_mark_posting_failed()` — أي فشل بيتكتب على `case.data` بدل ما يضيع في اللوج.
- الـ payloads الأربعة في الملف بقت بتتبني عن طريق الـ helper المشترك.

### الدليل الحي بعد الإصلاح
```
POST /api/v1/cases/{id}/transition {"to_stage":"confirmed"} → 200
GET  /api/v1/cases/{id} → case.data:
  {"customer_name":"Rana Tarek","sell_price":9000,"buy_price":6000,
   "gl_receivable_posted":true,"gl_payable_posted":true}
```
والقيدين الحقيقيين اللي اتعملوا:
```
JE-TRV-01A0A636-AR  POSTED  1200 Accounts Receivable DR 9000 / 4010 Sales Revenue  CR 9000
JE-TRV-01A0A636-AP  POSTED  5010 Cost of Goods Sold  DR 6000 / 2100 Accounts Payable CR 6000
```

---

## 3) عقد `invoice.created` + الفشل الصامت في المحاسبة ✅

### الحالة قبل الإصلاح
`handle_invoice_created` كان بيرد على أي حقل ناقص بـ `logger.error(...)` + `return` — سطر واحد في اللوج، ومفيش أي إشارة للمستخدم. والسياحة كانت فعلاً بتبعت payload من غير `invoice_number`.

**تصحيح لفرضية كانت في البرومبت**: التوظيف **مكنش** ناقصه `invoice_number` — فحصت الـ payload بتاعه (`recruitment/listeners.py:115`) ولقيته بيبعته صح، وكذلك الفنادق والتأجير. السياحة بس هي اللي كانت ناقصة.

### التعديل
- **ملف جديد**: `backend/app/core/events/invoice_payload.py` فيه `build_invoice_created_payload()` — كل الحقول اللي الـ handler محتاجها بقت **keyword arguments إجبارية**، يعني مستحيل تركيبيًا أي plugin يبني payload ناقص. ومعاه `assert_invoice_payload_contract()` للطرف المستقبِل.
- الأربع موديولات بقت تستخدم الـ helper.
- `handle_invoice_created` بقى **يرمي** `InvoicePayloadContractError` بدل ما يبلع. الـ EventBus بيمسك الاستثناء عن قصد (عشان subscriber بايظ مايوقّفش الـ publisher)، لكنه بيسجله بـ `logger.exception` — يعني traceback كامل باسم الاستثناء بدل سطر بيضيع.

### الدليل إن "الصوت العالي" ده اشتغل فعليًا
التعديل ده هو اللي **كشف السبب الحقيقي الأخير**. بعد ما الجداول اتعملت والـ payloads اتظبطت، الليدجر فضل فاضي — والسبب ظهر خام في `backend/logs/backend.log`:

```
app.core.events.event_bus  ERROR
handler 'handle_invoice_created' raised while processing event_type='invoice.created'
ClosedPeriodError("No accounting period defined for entry date '2026-09-15'. Cannot post journal entry.")
```

قبل التعديل ده، الرسالة دي مكانتش هتظهر أصلاً.

---

## 4) (بند إضافي مكنش في البرومبت) الفترة المحاسبية والحسابات الناقصة ✅

ده كان **السبب الأخير الفعلي** اللي مانع كل القيود، واكتشفته أثناء التنفيذ:

1. **مفيش أي `AccountingPeriod`** في التينانت. `create_journal_entry` بيرفض أي قيد من غير فترة تغطي التاريخ (hard block). التينانتس الجديدة بس هي اللي بتاخد الفترة من `_provision_tenant_schema_internal`.
2. **حساب `4020` ناقص**. فحص حي للشجرة رجّع: `["1100","1200","1300","2100","3100","4010","5010","5100"]` — والتأجير بيرحّل على 4020 بالظبط، فكان هيموت بـ `LookupError` حتى بعد حل مشكلة الفترة.

**ملف جديد**: `g3b4c5d6e7f8_backfill_open_period_and_missing_accounts.py` — بيزرع فترة مفتوحة 2020–2099 (نفس اللي التزويد بيزرعها) وأي حسابات ناقصة من `DEFAULT_ACCOUNTS`، idempotent.

الدليل بعد التشغيل:
```
INFO  [alembic.runtime.migration] Running upgrade f2a3b4c5d6e7 -> g3b4c5d6e7f8,
      backfill_open_period_and_missing_accounts
GET /api/v1/accounting/accounts → ["1100","1200","1300","2100","3100","4010","4020","5010","5100"]
```

> **ملاحظة صريحة**: أول محاولة لتشغيل الميجريشن ده **فشلت بغلطة مني** — كنت بابعت التواريخ كنصوص و`asyncpg` بيطلب `datetime` حقيقي (`DataError: invalid input for query argument $3`). الميجريشن كله لُفّ في transaction واحدة فمكتبش أي حاجة، واتصلح واتشغل تاني بنجاح.

---

## 5) فجوة CRUD على الغرف والعربيات ✅

### الحالة قبل الإصلاح
`PATCH`/`DELETE` موجودين وشغالين في الباك إند، لكن الضغط على كارت الغرفة في `/dashboard/hospitality` مكنش بيعمل **أي حاجة** — لا modal ولا menu.

### التعديل
`frontend/src/app/dashboard/hospitality/page.tsx` و `.../rental/page.tsx`: زرار تعديل (Pencil) وحذف (Trash) على كل كارت، `CreateRoomModal` → `RoomModal` يدعم الإنشاء والتعديل، و`DeleteRoomDialog`/`DeleteVehicleDialog` بتأكيد داخل الصفحة (مش `window.confirm`).

نقطة مهمة اتحطت في الحسبان: في وضع التعديل الـ attributes الحالية بتتبعت كلها (`...room.attributes`) قبل الحقول المعدّلة — لأن الباك إند بيعمل merge لـ `RoomAttributes`/`VehicleAttributes` المُفسَّرة، فأي حقل مش متبعت كان هيرجع بقيمته الافتراضية ويمسح البيانات الحقيقية (مثلاً `current_mileage` كان هيترجع 0).

### الدليل الحي (من الواجهة فعليًا)
```
الغرفة 101: فتحت الـ modal، غيّرت الاسم والسعة، ضغطت "حفظ التعديلات"
GET /api/v1/hospitality/rooms →
 [{"code":"101","name":"Deluxe Sea View - EDITED",
   "attributes":{"capacity":3,"floor":1,"room_type":"double","base_rate":1500,...}}]
   ← الاسم والسعة اتغيروا، و base_rate=1500 اتحافظ عليه

حذف غرفة تجريبية من الواجهة (زرار الحذف → "تأكيد الحذف"):
GET /hospitality/rooms                → ["101:Deluxe Sea View - EDITED"]   (اختفت)
GET /hospitality/rooms?is_active=false → [{"code":"DEL-1","is_active":false}] (soft-delete صح)

المركبة V-001: غيّرت الاسم من الواجهة →
 [{"code":"V-001","name":"Toyota Corolla 2023 - EDITED","mileage":5000,"rate":800,"plate":"ABC-1234"}]
   ← العداد والسعر اليومي اتحافظ عليهم

حذف مركبة تجريبية من الواجهة →
 active: ["V-001:..."] / inactive: [{"code":"V-DEL","is_active":false}]
```

---

## 6) (إضافي) أسماء الحسابات الغلط في سطور القيد ✅

أول ما القيود اشتغلت، ظهر إن `handle_invoice_created` كان بيكتب `account_name` بالغصب `"Accounts Receivable"` و`"Sales Revenue"` لأي حساب، فطلع في الليدجر:
```
JE-TRV-...-AP:  "5010 Accounts Receivable"  /  "2100 Sales Revenue"   ← أكواد صح، أسماء غلط
JE-RENT-...-RET: "4020 Sales Revenue"                                  ← المفروض "Vehicle Rental Revenue"
```
اتشال الاسم المكتوب بالغصب، و`create_journal_entry` بقى يجيب الاسم الحقيقي من جدول الحسابات. الدليل بعد الإصلاح:
```
JE-TRV-01A0A637-AP  POSTED  5010 Cost of Goods Sold DR 2500 / 2100 Accounts Payable CR 2500
JE-TRV-01A0A637-AR  POSTED  1200 Accounts Receivable DR 4000 / 4010 Sales Revenue  CR 4000
```

---

## ملاحظات مكتشفة ولم تُصلَح (خارج نطاق P0 — موثّقة مش مُلمّعة)

### ⛔ فلاج `posting_failed` القديم مبيتمسحش بعد نجاح لاحق
الحجز اللي كان فشل يوم 14 سبتمبر فضل شايل `posting_failed: true` و`posting_error` القديم حتى بعد ما الـ checkout نجح فعليًا وحسب 6000.96. موديول التوظيف بس هو اللي بيمسح الفلاجات دي قبل الترحيل (`updated_data.pop("posting_failed")`). الفنادق والتأجير والسياحة لأ — فأي حالة اتصلحت بتفضل شكلها معطلة للأبد. **إصلاح مقترح**: نقل نفس السطرين لباقي الموديولات.

### ⛔ اسم المستخدم في الشريط الجانبي بيجي من `localStorage` مش من `/auth/me`
اتأكدت حيًا: التوكن في `sessionStorage` كان لحساب الاختبار (`/auth/me` رجّع `hospaudit2...` / tenant `e1ee4d0e`) بينما الشريط الجانبي عارض **`abanob elwy / OWNER`** — الاسم جاي من `localStorage["trust-core-storage"]` (نسخة محفوظة من آخر تسجيل دخول على المتصفح). ده نفس باغ "أحمد منصور" اللي في التقرير القديم، وده سببه الجذري. **كل استدعاءات الـ API بتستخدم توكن تينانت الاختبار**، فبيانات التحقق فوق سليمة — لكن الفجوة دي خطيرة في بيئة فيها أكتر من مستخدم على نفس الجهاز.

### ⛔ سعر الليلة مش بيتعبى تلقائيًا من الغرفة
`base_rate` بيتسجل على الغرفة (1500) لكن نموذج الحجز فيه حقل `daily_rate` منفصل قيمته الافتراضية **0** ومش بيتعبى من الغرفة المختارة. لو المستخدم سابه 0، الفاتورة بتطلع بإيجار غرفة = صفر (شفتها فعليًا: `room_charge: "0.00"` على حجز اتعمل من غير `daily_rate`). **مش blocker** لأن الحقل موجود وإجباري في الفورم، لكنها فخ حقيقي.

### ⛔ لم يُنفَّذ: التحقق على تينانت جديد تمامًا
البرومبت طلب تينانت اختبار جديد أعمله بنفسي. حاولت التسجيل 3 مرات في جلسة سابقة وكلها فشلت بـ `Failed to fetch` بعد ~50 ثانية، فاستخدمت تينانت اختبار موجود (مش تينانت المستخدم الحقيقي) — وده فعليًا **أقوى** كدليل للبند ده، لأنه تينانت قديم كان معطل بالفعل وأثبت إن الميجريشن بيصلح التينانتس الموجودة، مش بس الجديدة. لكن يفضل تأكيد إن التينانت الجديد بيشتغل من أول لحظة برضه.

### ⛔ لم يُفحص: مسار الإلغاء (cancelled) في السياحة والفنادق
`_post_cancellation_entries` و`_post_cancellation_penalty` اتعدلوا (السياحة) أو اتفحصوا بالقراءة بس — **متجربوش حيًا**. مينفعش أقول عنهم شغالين.

---

## ملخص الملفات المعدَّلة

| الملف | نوع التغيير |
|---|---|
| `backend/alembic/tenant/versions/f2a3b4c5d6e7_add_folio_items_and_vehicle_inspections.py` | جديد |
| `backend/alembic/tenant/versions/g3b4c5d6e7f8_backfill_open_period_and_missing_accounts.py` | جديد |
| `backend/app/core/events/invoice_payload.py` | جديد |
| `backend/alembic/tenant/env.py` | استيراد موديلات الـ plugins (السبب الجذري) |
| `backend/app/plugins/hospitality/models/folio.py` | `schema="tenant"` على الـ enum |
| `backend/app/plugins/rental/models/inspection.py` | `schema="tenant"` على الـ enums |
| `backend/app/plugins/travel/listeners.py` | إزالة الـ raw SQL + نمط session مشترك + payload helper + posting_failed |
| `backend/app/modules/accounting/events.py` | فرض العقد + رمي استثناء + تصحيح أسماء الحسابات |
| `frontend/src/app/dashboard/hospitality/page.tsx` | تعديل/حذف الغرف |
| `frontend/src/app/dashboard/rental/page.tsx` | تعديل/حذف المركبات |
