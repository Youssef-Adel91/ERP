# Nexus ERP — Design Tokens (Stitch direction_6, المعتمد)

هذا هو مرجع التصميم **الفعلي المطبَّق** في `frontend/` الحالي. المصدر الرسمي للتوكنز هو
`stitch_egyptian_erp_design_system_generator/stitch_egyptian_erp_design_system_generator/direction_6_*/code.html`
(10 ملفات، كلها بنفس التوكنز بالظبط — تم التحقق برمجيًا 2026-08-09).

> ملاحظة: فيه ملف `DESIGN_TOKENS.md` تاني في جذر المشروع (`../DESIGN_TOKENS.md`) — ده بتاع نظام تصميم **قديم** ("Trust Core" بألوان ink/accent/paper) كان مستخدم في `frontend_old/` بس، ومش مطبَّق في `frontend/` الحالي خالص. اتجاهله، ده مرجع الحقيقي.

---

## الألوان (Material Design 3 — 47 توكن، مطابقة 100% لملفات Stitch)

كل القيم دي موجودة فعليًا في `frontend/src/app/globals.css` (تحت `:root`) ومربوطة في `frontend/tailwind.config.ts`. اتأكد بالمقارنة البرمجية إنها مطابقة حرفيًا (نفس القيم الست عشرية) للـ 10 ملفات المرجعية.

| Token | القيمة | الاستخدام النموذجي |
|---|---|---|
| `primary` | `#00288e` | الأزرار الأساسية، العنصر النشط في القائمة، الروابط |
| `on-primary` | `#ffffff` | نص فوق `primary` |
| `primary-container` | `#1e40af` | خلفيات أيقونات مميزة، شارات |
| `on-primary-container` | `#a8b8ff` | نص فوق `primary-container` |
| `secondary` | `#006a61` | مؤشرات إيجابية (trend up)، حالات "نشط" |
| `secondary-container` | `#86f2e4` | خلفيات خفيفة لمؤشرات إيجابية |
| `tertiary` | `#440098` | لون ثالث للتنويع البصري (رسوم بيانية، أيقونات) |
| `tertiary-container` | `#5f00d1` | خلفيات مرتبطة بـ tertiary |
| `error` | `#ba1a1a` | أخطاء، مؤشرات سلبية، حذف |
| `error-container` | `#ffdad6` | خلفيات خفيفة للأخطاء |
| `background` / `surface` | `#f8f9fa` | خلفية الصفحة |
| `on-surface` | `#191c1d` | نص أساسي |
| `on-surface-variant` | `#444653` | نص ثانوي |
| `surface-container-lowest` | `#ffffff` | الكروت البيضاء |
| `surface-container-low` | `#f3f4f5` | رؤوس الجداول، خلفيات هادئة |
| `surface-container` / `-high` / `-highest` | `#edeeef` / `#e7e8e9` / `#e1e3e4` | طبقات تظليل متدرجة |
| `outline` | `#757684` | حدود، أيقونات ثانوية، نص خافت |
| `outline-variant` | `#c4c5d5` | حدود خفيفة (hairlines) |

القائمة الكاملة (47 توكن) موجودة في `globals.css`. **الإضافات الوحيدة** فوق نظام Stitch الرسمي هي `success`/`success-bg` و`warning`/`warning-bg` (لأن Stitch نفسه بيعيد استخدام `secondary`/`error` كمؤشرات إيجابي/سلبي بدل ما يعرّف ألوان حالة مخصصة) — دول إضافيين آمنين ومتوافقين بصريًا، مش تعارض.

---

## الخطوط

```
Manrope   → العناوين (headline-sm/md/lg)
Inter     → كل النصوص العادية (body-sm/md/lg, data-mono, label-caps)
```

محمّلين فعليًا في `frontend/src/app/layout.tsx` عبر `next/font/google`. القيم بالبكسل (`fontSize`) مطابقة حرفيًا لملفات Stitch:

| Token | الحجم | الوزن |
|---|---|---|
| `headline-lg` | 28px / lh 36px | 700 |
| `headline-md` | 20px / lh 28px | 600 |
| `headline-sm` | 16px / lh 24px | 600 |
| `body-lg` | 16px / lh 24px | 400 |
| `body-md` | 14px / lh 20px | 400 |
| `body-sm` | 12px / lh 16px | 400 |
| `data-mono` | 14px / lh 20px | 600 (استخدمها لأي رقم/عملة، دايمًا مع `dir="ltr"`) |
| `label-caps` | 11px / lh 16px, letter-spacing 0.05em | 700 |

---

## Border Radius

Stitch الرسمي بيعرّف **4 قيم بس**: `DEFAULT` (4px)، `lg` (8px)، `xl` (12px)، `full` (دائري كامل). التطبيق الحالي عنده كمان `sm` و`md` و`2xl` كإضافات — استخدمها بحذر، لكن **الكروت والعناصر الرئيسية في كل الصفحات لازم تستخدم `rounded-xl` بالظبط زي المرجع، مش `rounded-2xl`** (كان فيه انحراف بسيط عن كده في نسخة تجريبية سابقة من `dashboard/page.tsx`، تم تصحيحه).

## Spacing

`base` (4px), `compact-padding` (8px), `gutter` (16px), `card-padding` (20px), `container-margin` (24px) — مطابقة حرفيًا لـ Stitch.

---

## مكونات متكررة (مستخرجة من الـ 10 مرجعيات)

- **الهيدر (TopNavBar)**: ثابت (`fixed top-0`)، ارتفاع `h-16`، خلفية `bg-surface`، حد سفلي `border-outline-variant`، شعار "Nexus ERP" بلون `text-primary` و`font-headline-md`.
- **القائمة الجانبية (SideNavBar)**: عرض `w-64`، خلفية بيضاء، العنصر النشط: `bg-secondary-container text-on-secondary-container border-r-4 border-primary`. زرار تسجيل الخروج في الأسفل بلون `text-error`.
- **الكروت**: كلاس `.glass-card` (شفافية 95% + `backdrop-blur` + حد `outline-variant`) مع `p-card-padding rounded-xl shadow-sm hover:shadow-md`.
- **بادجات الحالة**: `px-2 py-0.5 rounded` بخلفية شفافة من لون الحالة (`bg-secondary-container/20 text-secondary` لإيجابي، `bg-error-container/20 text-error` لسلبي).
- **الجداول**: رأس بخلفية `surface-container-low`، صفوف بفاصل `divide-outline-variant/30`، hover بخلفية `surface-container-lowest`.

هذه الأنماط اتلخّصت في مكونات React مشتركة تحت `frontend/src/components/ui/` (`Card`, `Badge`, `DataTable`) — استخدمها بدل تكرار الـ classNames في كل صفحة.
