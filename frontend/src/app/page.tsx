"use client";

import { useEffect, useState } from "react";
import { SUPPORT_EMAIL } from "@/lib/brand";
import Link from "next/link";
import Image from "next/image";
import {
  Wallet, TrendingUp, Package, Users, Plane, Coffee, Car, ShieldCheck,
  ArrowLeft, CheckCircle2, Mail, Receipt, Store, Building2, CreditCard,
  PackageCheck, CalendarClock, Languages,
  Layers, BookCheck, Bot,
} from "lucide-react";

// ── Data ──────────────────────────────────────────────────────────────────────
const modules = [
  { icon: Wallet, title: "المحاسبة والمالية", desc: "دفتر أستاذ، قيود تلقائية متوازنة، وتقارير مالية لحظية.", badge: "الأساس" },
  { icon: Receipt, title: "الفاتورة الإلكترونية", desc: "إصدار الفواتير بصيغة منظومة مصلحة الضرائب المصرية (ETA).", badge: "ETA" },
  { icon: TrendingUp, title: "المبيعات وعروض الأسعار", desc: "العملاء، العروض، الفواتير، التحصيل والمرتجعات.", badge: null },
  { icon: Store, title: "نقاط البيع (POS)", desc: "واجهة سريعة للكاشير مع دعم الباركود والطابعات.", badge: null },
  { icon: Package, title: "المخزون والمستودعات", desc: "تتبع الأصناف، المخازن المتعددة، أوامر الشراء وتقييم المخزون.", badge: null },
  { icon: Users, title: "الموارد البشرية", desc: "التوظيف، الرواتب والاستقطاعات، مع قيود محاسبية تلقائية.", badge: null },
  { icon: PackageCheck, title: "الشحن والتوصيل", desc: "ربط شركات الشحن المحلية وتتبع الطلبات.", badge: null },
  { icon: Building2, title: "إدارة الفروع", desc: "لوحة مركزية لمتابعة كل الفروع من مكان واحد.", badge: null },
  { icon: Plane, title: "السياحة والسفر", desc: "حجوزات، تسعير ومتابعة ملفات العملاء.", badge: null },
  { icon: Coffee, title: "المطاعم والضيافة", desc: "حجوزات الغرف، الرسوم والفوترة عند المغادرة.", badge: null },
  { icon: Car, title: "تأجير السيارات", desc: "إدارة الأسطول والعقود والفوترة.", badge: null },
  { icon: CreditCard, title: "الاشتراك والفوترة", desc: "خطط الاشتراك وفواتير العملاء الدورية.", badge: null },
];

const sectors = [
  { icon: Layers, title: "شركات الخدمات", desc: "محاسبة · موارد بشرية · اشتراكات" },
  { icon: Car, title: "تأجير السيارات", desc: "أسطول · عقود · فوترة" },
  { icon: Plane, title: "السياحة والسفر", desc: "حجوزات · تسعير · عملاء" },
  { icon: Coffee, title: "المطاعم والفنادق", desc: "حجوزات · نقاط بيع · فوترة" },
  { icon: Store, title: "التجزئة والتجارة", desc: "POS · مخزون · فاتورة إلكترونية" },
];

const facts = [
  { value: "29", label: "تقريرًا جاهزًا بالشات" },
  { value: "Excel · CSV · PDF", label: "تنزيل أي تقرير" },
  { value: "RTL", label: "عربي بالكامل من الأساس" },
  { value: "لكل شركة", label: "بياناتها معزولة تمامًا" },
];

const reasons = [
  { icon: Bot, title: "اسأل بالعربي واستلم التقرير", desc: "اكتب «أعمار الديون» أو «أرباح الشهر اللي فات» وتاخد جدول بأرقام من دفاترك الفعلية، مش تقديرات." },
  { icon: CalendarClock, title: "تقارير تصلك على الإيميل", desc: "جدول أي تقرير يوميًا أو أسبوعيًا أو شهريًا، وتوصل لك ولمحاسبك بملف Excel جاهز." },
  { icon: BookCheck, title: "قيود محاسبية تلقائية", desc: "كل فاتورة وتحصيل ومرتجع وراتب بيترحّل لقيد متوازن. ميزان المراجعة دايمًا مضبوط." },
  { icon: ShieldCheck, title: "صلاحيات حسب الدور", desc: "المالك والمحاسب والمبيعات والمخازن، كل واحد يشوف ويعمل اللي يخصه بس — حتى في المساعد الذكي." },
  { icon: Layers, title: "اشترك فيما تحتاجه", desc: "ابدأ بالمحاسبة والمبيعات، وأضف المخزون أو الموارد البشرية أو الفروع لما تكبر." },
  { icon: Languages, title: "مصمم للسوق المصري", desc: "ضريبة القيمة المضافة، الشيكات، الأجور، والفاتورة الإلكترونية — مش نظام عام محتاج تعديل." },
];

// ── Navbar ───────────────────────────────────────────────────────────────────
function Logo({ small = false }: { small?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <div className={`${small ? "w-8 h-8" : "w-9 h-9"} bg-primary rounded-xl flex items-center justify-center`}>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className={`${small ? "w-4 h-4" : "w-5 h-5"} fill-white`}>
          <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z" />
        </svg>
      </div>
      <span className="font-bold text-lg tracking-tight text-on-surface">Trust Core</span>
    </Link>
  );
}

function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 8);
    handler();
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <header className={`fixed top-0 w-full z-50 bg-surface-container-lowest/90 backdrop-blur-md border-b transition-colors ${scrolled ? "border-outline-variant" : "border-transparent"}`}>
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between" dir="rtl">
        <Logo />
        <nav className="hidden md:flex items-center gap-7 text-sm font-medium text-on-surface-variant">
          {[["الوحدات", "#modules"], ["المساعد الذكي", "#ai"], ["المميزات", "#why"], ["الأسعار", "#pricing"]].map(([label, href]) => (
            <a key={href} href={href} className="hover:text-primary transition-colors">{label}</a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/login" className="hidden sm:block text-sm font-semibold px-4 py-2 rounded-lg text-on-surface hover:bg-surface-container transition-colors">
            تسجيل الدخول
          </Link>
          <Link href="/register" className="bg-primary text-on-primary text-sm font-bold px-5 py-2 rounded-lg hover:bg-primary-container transition-colors">
            ابدأ مجانًا
          </Link>
        </div>
      </div>
    </header>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#FBF8F3] dark:bg-surface-container-lowest overflow-x-hidden font-sans text-on-surface" dir="rtl">
      <Navbar />

      {/* ── HERO (photo + systems marketplace) ──────────────────────────────── */}
      <section className="relative isolate overflow-hidden bg-[#00071C] pt-28 md:pt-32 pb-20 text-white">
        <div className="absolute inset-x-0 top-0 h-[760px] -z-10" aria-hidden>
          <Image src="/hero-bg.jpg" alt="" fill priority sizes="100vw" className="object-cover object-left" />
          <div className="absolute inset-0 bg-gradient-to-l from-[#00071C] via-[#00071C]/75 to-[#00071C]/30 lg:via-[#00071C]/45 lg:to-transparent" />
          <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-[#00071C] to-transparent" />
        </div>

        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-2xl pb-14 md:pb-20">
            <p className="inline-block text-sm font-semibold text-[#C7D0FF] bg-white/10 rounded-full px-4 py-1.5 mb-6">
              منصة أنظمة متكاملة لأي نشاط تجاري
            </p>
            <h1 className="text-4xl md:text-6xl font-black leading-[1.2] tracking-tight mb-6">
              كل أنظمة شغلك في مكان واحد
            </h1>
            <p className="text-lg md:text-xl text-white/75 leading-relaxed mb-9">
              محاسبة، مخزون، فاتورة إلكترونية، موارد بشرية، مطاعم وفنادق، سياحة وتأجير سيارات. اختار الأنظمة اللي محتاجها دلوقتي، وزوّد غيرها وقت ما تكبر.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 mb-6">
              <Link href="/register" className="inline-flex items-center justify-center gap-2 bg-primary text-on-primary font-bold text-base px-8 py-3.5 rounded-xl hover:bg-primary-container transition-colors">
                ابدأ مجانًا
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <a href="#modules" className="inline-flex items-center justify-center gap-2 border border-white/35 text-white font-semibold text-base px-8 py-3.5 rounded-xl hover:bg-white/10 transition-colors">
                استعرض الأنظمة
              </a>
            </div>
            <p className="text-sm text-white/65 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-[#9AA8FF]" />
              بدون بطاقة ائتمان
            </p>
          </div>

          <div id="modules" className="scroll-mt-24 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {modules.map((mod) => (
              <div key={mod.title} className="rounded-2xl border border-white/15 bg-white/[0.07] backdrop-blur-sm p-5 hover:bg-white/[0.11] transition-colors">
                <div className="flex items-start justify-between mb-4">
                  <div className="w-11 h-11 rounded-xl bg-white/10 border border-white/15 flex items-center justify-center">
                    <mod.icon className="w-5 h-5 text-[#C7D0FF]" />
                  </div>
                  <Link href="/register" className="text-[13px] font-bold bg-white/15 hover:bg-white/25 rounded-full px-3 py-1 transition-colors">+ أضف</Link>
                </div>
                <h3 className="font-bold text-lg mb-1">{mod.title}</h3>
                <p className="text-sm text-white/65 leading-relaxed">{mod.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FACTS ──────────────────────────────────────────────────────────── */}
      <section className="border-y border-outline-variant bg-[#F3ECE1] dark:bg-surface-container-low">
        <div className="max-w-7xl mx-auto px-6 py-8 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {facts.map((f) => (
            <div key={f.label}>
              <p className="text-xl md:text-2xl font-black text-on-surface" dir="auto">{f.value}</p>
              <p className="text-sm text-on-surface-variant mt-1">{f.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── SECTORS ─────────────────────────────────────────────────────────── */}
      <section id="sectors" className="py-20">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-4xl font-black mb-3">مناسب لنشاطك، أيًا كان</h2>
          <p className="text-lg text-on-surface-variant mb-12">كل قطاع بيبدأ بمجموعة أنظمة جاهزة، وتقدر تعدّلها في أي وقت.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 text-start">
            {sectors.map((sec) => (
              <div key={sec.title} className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-5">
                <div className="w-10 h-10 rounded-xl bg-primary-fixed flex items-center justify-center mb-4">
                  <sec.icon className="w-5 h-5 text-primary" />
                </div>
                <h3 className="font-bold text-lg mb-1">{sec.title}</h3>
                <p className="text-sm text-on-surface-variant">{sec.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── AI ─────────────────────────────────────────────────────────────── */}
      <section id="ai" className="py-24 bg-[#F3ECE1] dark:bg-surface-container-low">
        <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-14 items-center">
          <div>
            <p className="text-sm font-semibold text-primary mb-4">المساعد الذكي</p>
            <h2 className="text-3xl md:text-4xl font-black mb-5 leading-tight">اسأل بالعربي، واستلم تقرير جاهز للتنزيل</h2>
            <p className="text-lg text-on-surface-variant mb-8 leading-relaxed">
              المساعد بيقرأ من دفاترك الفعلية، فكل رقم تشوفه له مصدر. وبيحترم الصلاحيات: كل موظف يشوف التقارير المسموحة لدوره بس.
            </p>
            <ul className="space-y-4">
              {[
                "أرباح وخسائر، ميزانية، ضريبة، تدفق نقدي، أعمار ديون العملاء والموردين",
                "كشف حساب لأي عميل أو مورد بمجرد كتابة اسمه",
                "تنزيل Excel وCSV وPDF، أو جدولة التقرير على الإيميل",
                "شغّال حتى قبل ربط أي نموذج ذكاء اصطناعي — والنموذج بيحسّن الفهم والصياغة",
              ].map((t) => (
                <li key={t} className="flex items-start gap-3 text-on-surface">
                  <CheckCircle2 className="w-5 h-5 text-primary mt-0.5 shrink-0" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {["أعمار الديون", "أرباح الشهر اللي فات", "الأصناف الأكثر مبيعًا", "ملخص ضريبة القيمة المضافة", "الشيكات المستحقة خلال 14 يوم", "تقييم المخزون", "أعمار الدائنين", "الملخص اليومي"].map((q) => (
              <div key={q} className="rounded-xl border border-outline-variant bg-surface-container-lowest px-4 py-3 text-sm font-medium text-on-surface">
                {q}
              </div>
            ))}
            <p className="col-span-2 text-xs text-on-surface-variant mt-1">أمثلة على أسئلة بيفهمها المساعد.</p>
          </div>
        </div>
      </section>

      {/* ── WHY ────────────────────────────────────────────────────────────── */}
      <section id="why" className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-2xl mb-14">
            <h2 className="text-3xl md:text-4xl font-black mb-4">ليه Trust Core؟</h2>
            <p className="text-lg text-on-surface-variant">اللي بنقوله هنا موجود فعلًا في النظام.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-10 gap-y-10">
            {reasons.map((r) => (
              <div key={r.title} className="flex gap-4">
                <div className="w-11 h-11 shrink-0 rounded-xl bg-primary-fixed text-primary flex items-center justify-center">
                  <r.icon className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold mb-1.5">{r.title}</h3>
                  <p className="text-sm text-on-surface-variant leading-relaxed">{r.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING ────────────────────────────────────────────────────────── */}
      <section id="pricing" className="py-24 bg-[#F3ECE1] dark:bg-surface-container-low">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-black mb-4">ابدأ مجانًا، وادفع لما تكبر</h2>
            <p className="text-lg text-on-surface-variant max-w-2xl mx-auto">اشتراك شهري بسيط حسب الوحدات اللي بتستخدمها فعلًا.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 items-stretch">
            {[
              { name: "Starter", price: "299", desc: "لأصحاب المشاريع والمتاجر الصغيرة", features: ["5 مستخدمين", "3 وحدات", "10,000 فاتورة/شهر", "دعم عبر الواتساب"] },
              { name: "Business", price: "899", desc: "للشركات المتنامية", features: ["25 مستخدمًا", "كل الوحدات", "فواتير غير محدودة", "المساعد الذكي والتقارير", "دعم أولوية"], popular: true },
              { name: "Enterprise", price: "مخصص", desc: "للمجموعات والشركات الكبرى", features: ["مستخدمين غير محدودين", "فروع غير محدودة", "تكامل مخصص", "مدير حساب مخصص"] },
            ].map((plan) => (
              <div key={plan.name} className={`relative rounded-2xl p-6 border flex flex-col ${plan.popular ? "border-primary bg-surface-container-lowest shadow-lg ring-1 ring-primary" : "border-outline-variant bg-surface-container-lowest"}`}>
                {plan.popular && <span className="absolute -top-3 right-6 bg-primary text-on-primary text-xs font-bold px-3 py-1 rounded-full">الأكثر اختيارًا</span>}
                <h3 className="font-black text-xl mb-1">{plan.name}</h3>
                <p className="text-sm text-on-surface-variant mb-5">{plan.desc}</p>
                <div className="text-3xl font-black mb-6">
                  {plan.price === "مخصص" ? plan.price : <>{plan.price}<span className="text-sm font-normal text-on-surface-variant mr-1">ج.م / شهر</span></>}
                </div>
                <ul className="space-y-2.5 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-on-surface-variant">
                      <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/register" className={`block w-full py-3 rounded-xl font-bold text-center transition-colors ${plan.popular ? "bg-primary text-on-primary hover:bg-primary-container" : "border border-outline-variant text-on-surface hover:bg-surface-container"}`}>
                  ابدأ الآن
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ────────────────────────────────────────────────────────────── */}
      <section className="py-20">
        <div className="max-w-4xl mx-auto px-6">
          <div className="rounded-3xl bg-primary text-on-primary text-center px-6 py-14">
            <h2 className="text-3xl md:text-4xl font-black mb-4">جاهز تنظّم شغلك؟</h2>
            <p className="text-lg text-on-primary/80 mb-8 max-w-xl mx-auto">أنشئ حسابك في دقايق وابدأ بفاتورتك الأولى.</p>
            <Link href="/register" className="inline-flex items-center gap-2 bg-surface-container-lowest text-primary font-black text-lg px-10 py-4 rounded-xl hover:opacity-90 transition-opacity">
              أنشئ حسابك المجاني
              <ArrowLeft className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-outline-variant py-12 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
            <div className="col-span-2 md:col-span-1">
              <div className="mb-4"><Logo small /></div>
              <p className="text-sm leading-relaxed text-on-surface-variant">المرجع الرقمي للتاجر المصري — نظام إدارة متكامل مصنوع للسوق المصري.</p>
            </div>
            {[
              { title: "الأنظمة", links: ["المحاسبة", "المبيعات", "المخزون", "الموارد البشرية", "الفاتورة الإلكترونية"] },
              { title: "الشركة", links: ["عن Trust Core", "اتصل بنا"] },
              { title: "الدعم", links: ["مركز المساعدة", "شروط الخصوصية"] },
            ].map((col) => (
              <div key={col.title}>
                <h4 className="font-bold mb-4 text-sm">{col.title}</h4>
                <ul className="space-y-2">
                  {col.links.map((link) => (
                    <li key={link}><a href="#" className="text-sm text-on-surface-variant hover:text-primary transition-colors">{link}</a></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="border-t border-outline-variant pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-on-surface-variant">
            <p>© {new Date().getFullYear()} Trust Core. جميع الحقوق محفوظة.</p>
            <a href={`mailto:${SUPPORT_EMAIL}`} className="flex items-center gap-1.5 hover:text-primary transition-colors">
              <Mail className="w-3.5 h-3.5" />
              {SUPPORT_EMAIL}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
