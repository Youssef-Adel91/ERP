# حالة نظام السياحة والسفر — جولة الجاهزية التجارية
**التاريخ**: 2026-09-09  
**المشروع**: Nexus ERP (OmniERP)  
**الوحدة**: `backend/app/plugins/travel` + `frontend/src/app/dashboard/travel`

---

## ما اتعمل في هذه الجولة

### 1. رفع مستندات التأشيرات (فجوة حرجة — مغلقة)

| الملف | التغيير |
|---|---|
| `backend/app/plugins/travel/models/document.py` | [جديد] موديل VisaDocument — تخزين الملفات كـ BYTEA في PostgreSQL |
| `backend/app/plugins/travel/api_visas.py` | 4 endpoints جديدة: رفع / قائمة / تحميل / حذف مستندات |
| Migration A1b2c3d4e5f6 | [جديد] idempotent migration |
| `frontend/src/app/dashboard/travel/visas/page.tsx` | صفوف قابلة للتوسعة تعرض المستندات + زر رفع مع تحقق client-side |

الأنواع المقبولة: PDF, JPEG, PNG, GIF, DOC, DOCX — حجم أقصى: 5 MB.
التخزين في DB-BYTEA مناسب حالياً؛ قابل للترحيل لـ S3 لاحقاً بتغيير storage backend فقط.

### 2. بيانات ركاب منظمة — Passenger Manifest

| الملف | التغيير |
|---|---|
| `backend/app/plugins/travel/models/passenger.py` | [جديد] موديل TravelPassenger مع FK اختياري للتأشيرة |
| `backend/app/plugins/travel/api_passengers.py` | [جديد] CRUD: قائمة / إضافة / تعديل / حذف |
| Migration A1b2c3d4e5f6 | يشمل جدول travel_passengers |
| `backend/app/main.py` | تسجيل travel_passengers_router (19d) |

يعمل بالتوازي مع passenger_manifest الموجود في Case.data JSONB.
حذف soft لو الراكب مرتبط بتأشيرة، حذف نهائي لو لأ.

### 3. حماية البيانات المالية من الحذف النهائي

- `api_visas.py/delete_visa`: soft delete لو fee_charged > 0 أو cost > 0
- `api_packages.py/delete_package`: soft delete دايماً (is_active=False)
- `list_visas`, `list_case_visas`, `list_packages`: يستبعدون is_active=False افتراضياً
- Migration: يضيف is_active على travel_visa_applications مع backfill

### 4. BSP وعمولات الموردين المعقدة — مؤجل عمداً

قرار عمل معلّق: لم يُحدَّد بعد إن كان النظام سيبيع تذاكر طيران عبر BSP.
الكود الحالي سُيِّب كما هو. لو اتقرر تفعيل BSP لاحقاً يحتاج: GDS integration + BSP reporting + عمولات متدرجة.

### 5. RBAC على موديول السياحة

- كل endpoints في api_visas, api_packages, api_passengers, api.py تتطلب CurrentUser
- delete_visa: مقيّد بـ OWNER, ADMIN
- delete_package: مقيّد بـ OWNER, ADMIN
- create_booking_from_package: مقيّد بـ OWNER, ADMIN, SALES

### 6. Pagination لقوائم الحجوزات

- cases/api/router.py/list_cases: limit (default 100, max 500) + offset (default 0)
- نفس النمط المستخدم في sales/api/payments.py

### 7. PDF تأكيد الحجز

- [جديد] travel/services/pdf_builder.py: دالة build_booking_confirmation_pdf()
- [جديد] GET /travel/bookings/{case_id}/pdf endpoint
- frontend: زر PDF بجانب التفاصيل لكل حجز

---

## التحقق الآلي

```
python -m ast: 11 ملف — جميعها سليمة (exit code 0)
npx tsc --noEmit: صفر أخطاء TypeScript (exit code 0)
```

---

## ما يحتاج تحقق حي على جهازك

### 1. تطبيق Migration
```bash
cd backend && alembic upgrade head
```

### 2. تأكد إن الجداول اتنشأت
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema LIKE 'tenant_%' 
  AND table_name IN ('travel_passengers', 'travel_visa_documents');
```

### 3. اختبار رفع مستند
افتح /dashboard/travel/visas، اضغط سهم التوسعة بجانب تأشيرة، ارفع PDF.

### 4. اختبار Soft Delete
احذف تأشيرة ذات رسوم عبر Swagger -> 204، is_active=False، مش تظهر في القائمة العادية.

### 5. اختبار PDF
افتح /dashboard/travel، اضغط "PDF" بجانب حجز.

### 6. اختبار Pagination
GET /api/v1/cases?case_type_id=...&limit=5&offset=0

---

## حالة الجاهزية التجارية

| المعيار | الحالة |
|---|---|
| رفع مستندات التأشيرة | مكتمل |
| CRUD ركاب منظم | Backend مكتمل |
| Soft delete للبيانات المالية | مكتمل |
| RBAC على موديول السياحة | مكتمل |
| Pagination لقوائم الحجوزات | مكتمل |
| PDF تأكيد الحجز | مكتمل |
| الأرقام المالية من باك إند حقيقي | كان موجوداً قبل هذه الجولة |
| تدفق بيع باقة → حجز → قيد محاسبي | كان موجوداً قبل هذه الجولة |
| BSP / تذاكر طيران | قرار مؤجل |
