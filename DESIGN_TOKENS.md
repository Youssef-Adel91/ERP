# Trust Core — Design Tokens Reference

مرجع سريع لاستخدام الـ tokens في `tailwind.config.ts` مع المشروع
(Next.js App Router + Tailwind + Shadcn UI، حسب `frontend_architecture_guide-v2.md`).

القيم دي مسحوبة مباشرة من ملف Figma (مش من عين)، فهي مطابقة 100% للتصميم المعتمد.

---

## الألوان — استخدام كل token فين بالظبط

| Token | القيمة | يُستخدم في |
|---|---|---|
| `ink` | `#040D1B` | خلفية القائمة الجانبية، عناوين الصفحات |
| `ink-500` | `#45474C` | النص الأساسي على الخلفيات الفاتحة |
| `ink-600` | `#1B1B1D` | نص عالي التمييز (أسماء، عناوين فرعية) |
| `ink-400` | `#75777D` | نص ثانوي/مساعد |
| `accent` | `#FF9800` | الأزرار الأساسية، العنصر النشط في القائمة، الروابط، الأيقونات المميزة |
| `accent-hover` | `#E6890A` | حالة hover/active على الأزرار |
| `accent-border` | `#653900` | خط التمييز الجانبي (border-right) للعنصر النشط في القائمة |
| `accent-tint` | `#FFF3E0` | خلفيات خفيفة (badges، hover على صفوف الجدول) |
| `paper` | `#FCF8FA` | خلفية الصفحة |
| `paper-card` | `#FFFFFF` | الكروت واللوحات |
| `paper-subtle` | `#F6F3F4` | رأس الجداول، خلفيات ثانوية |
| `paper-border` | `#C5C6CC` | الحدود الافتراضية |
| `paper-border-soft` | `#E4E2E3` | فواصل خفيفة (hairlines) |
| `sidebar-text` | `#BEC7DB` | نص روابط القائمة الجانبية (غير نشط) |
| `sidebar-subtitle` | `#818A9D` | "نظام إدارة المؤسسات" تحت الشعار |
| `success` / `success-bg` | `#2E7D32` / `#E8F5E9` | حالة "نشط"، "مكتمل"، "متوافق" |
| `danger` / `danger-bg` | `#BA1A1A` / `#FFEBEE` | حالة "متوقف"، "غير متوافق"، أرقام سلبية |
| `warning` / `warning-bg` | `#F9A825` / `#FFFDE7` | حالة "قيد المراجعة"، "قيد الانتظار" |

**القاعدة:** أي لون مش في الجدول ده معناه مش من نظام التصميم المعتمد — لو محتاج لون جديد، ارجع للألوان دي الأول وشوف لو تقدر تعبر عنه بيها قبل ما تضيف لون جديد.

---

## الخطوط

```ts
fontFamily: {
  sans: ["IBM Plex Sans Arabic", "IBM Plex Sans", "sans-serif"], // كل نصوص الواجهة (عربي + إنجليزي)
  mono: ["JetBrains Mono", "IBM Plex Mono", "monospace"],        // كل الأرقام والعملات فقط
}
```

**قاعدة مهمة:** أي رقم مالي أو عداد (أرصدة، أسعار، تواريخ رقمية) لازم يستخدم `font-mono` ويتعرض LTR حتى جوه الصفحة الـ RTL — استخدم:

```tsx
<span className="font-mono" dir="ltr">١٢,٤٥٠.٠٠</span>
```

### تحميل الخطوط في Next.js (`app/layout.tsx`)

الخطوط دي مش من Google Fonts القياسية بنفس الاسم — `IBM Plex Sans Arabic` موجود على Google Fonts، لكن `JetBrains Mono` كمان متاح. مثال التحميل:

```tsx
import { IBM_Plex_Sans_Arabic, JetBrains_Mono } from "next/font/google";

const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});
```

ثم في `tailwind.config.ts` تربط `fontFamily.sans`/`mono` بـ `var(--font-sans)` / `var(--font-mono)` بدل الاسم المباشر — أدق وأسرع في التحميل.

---

## الـ Border Radius

| Token | القيمة | يُستخدم في |
|---|---|---|
| `rounded-sm` | 2px | أزرار صغيرة، أيقونات مربعة |
| `rounded` (default) | 4px | الكروت، الجداول، معظم العناصر |
| `rounded-md` | 8px | صور/شعارات مربعة |
| `rounded-lg` | 12px | أفاتار دائري، شارات (badges) |
| `rounded-xl` | 16px | عناصر بارزة كبيرة |

---

## ملاحظات وتحذيرات

- **`accent-border` (`#653900`)**: ده لون قديم من قبل تصحيح الألوان (كان اللون الأساسي `#8B5000`)، وقف موجود بس كخط تمييز جانبي رفيع للعنصر النشط. شكله متناسق بصريًا مع `#FF9800` (ظل غامق منه)، فسبناه كما هو. لو حبيت توحّد الدرجات بدقة أكتر تقدر تولّد ظل غامق برمجيًا من `#FF9800` بدل القيمة الثابتة دي.
- **خطوط زيادة ظهرت في الفحص** (`Nimbus Sans`, `FreeSerif`): دي مش جزء من نظام التصميم — على الأغلب خطوط احتياطية (fallback) استخدمها Figma في حروف/رموز نادرة مش موجودة في IBM Plex Sans Arabic. تجاهلها.
- **RTL افتراضي**: الواجهة كلها مصممة عربي RTL كلغة أساسية، والإنجليزي LTR كلغة ثانوية عبر زرار تبديل. لما تبني الـ layout، استخدم `dir="rtl"` على `<html>` كافتراضي، وابني كل الـ spacing بمنطق منطقي (`ms-`/`me-` بدل `ml-`/`mr-`) عشان يتقلب صح مع اللغة.
