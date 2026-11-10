"use client";

import { useEffect, useState } from "react";
import { SUPPORT_EMAIL } from "@/lib/brand";
import Link from "next/link";
import {
  Wallet, TrendingUp, Package, Users, Plane, Coffee, Car, ShieldCheck,
  ArrowLeft, CheckCircle2, Mail, Receipt, Store, Building2, CreditCard,
  PackageCheck, FileSpreadsheet, Download, Printer, CalendarClock, Languages,
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

// ── Product preview (browser frame with a real-shaped report answer) ──────────
function ProductPreview() {
  const rows = [
    { c: "شركة الأمل للتجارة", d: "١٠ أكتوبر", a: "12,500.00" },
    { c: "مؤسسة النور", d: "٢٢ أكتوبر", a: "8,200.00" },
    { c: "متجر الحرية", d: "٢ نوفمبر", a: "4,750.00" },
  ];
  return (
    <div className="relative" dir="rtl">
      <div className="absolute -inset-4 -z-10 rounded-[2rem] bg-primary-fixed/70" aria-hidden />
      <div className="rounded-2xl border border-outline-variant bg-surface-container-lowest shadow-[0_28px_60px_-28px_rgba(11,20,112,0.35)] overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-outline-variant bg-surface-container-low">
          <div className="flex gap-1.5" aria-hidden>
            <span className="w-2.5 h-2.5 rounded-full bg-outline-variant" />
            <span className="w-2.5 h-2.5 rounded-full bg-outline-variant" />
            <span className="w-2.5 h-2.5 rounded-full bg-outline-variant" />
          </div>
          <div className="flex-1 text-center text-[11px] text-on-surface-variant bg-surface-container-lowest border border-outline-variant rounded-md py-1" dir="ltr">
            trustcore.app/dashboard/assistant
          </div>
        </div>

        <div className="p-4 space-y-3">
          <div className="grid grid-cols-3 gap-2">
            {[["مستحق من العملاء", "25,450"], ["مستحق للموردين", "18,900"], ["رصيد النقدية", "61,300"]].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-surface-container px-3 py-2">
                <p className="text-[10px] text-on-surface-variant">{k}</p>
                <p className="text-sm font-bold text-on-surface tabular-nums" dir="ltr">{v}</p>
              </div>
            ))}
          </div>

          <div className="flex justify-start">
            <div className="bg-primary text-on-primary text-[13px] rounded-2xl rounded-br-sm px-3.5 py-2 max-w-[80%]">
              إيه أعمار الديون عندي؟
            </div>
          </div>

          <div className="flex justify-end">
            <div className="w-full rounded-2xl rounded-bl-sm border border-outline-variant bg-surface-container-lowest p-3 space-y-2.5">
              <p className="text-[13px] text-on-surface leading-relaxed">
                إجمالي المستحق على العملاء <b>25,450 ج.م</b>، منها 8,200 متأخرة أكتر من 30 يوم.
              </p>
              <div className="rounded-lg border border-outline-variant overflow-hidden">
                <div className="flex items-center justify-between px-3 py-1.5 bg-surface-container-low border-b border-outline-variant">
                  <span className="text-[12px] font-semibold text-on-surface">أعمار الديون (العملاء)</span>
                  <div className="flex gap-1">
                    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-primary text-on-primary"><FileSpreadsheet className="w-3 h-3" />Excel</span>
                    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant"><Download className="w-3 h-3" />CSV</span>
                    <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-surface-container text-on-surface-variant"><Printer className="w-3 h-3" />PDF</span>
                  </div>
                </div>
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-on-surface-variant">
                      <th className="text-right font-medium px-3 py-1.5">العميل</th>
                      <th className="text-right font-medium px-3 py-1.5">الاستحقاق</th>
                      <th className="text-right font-medium px-3 py-1.5">المتبقي</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.c} className="border-t border-outline-variant/60">
                        <td className="px-3 py-1.5 text-on-surface">{r.c}</td>
                        <td className="px-3 py-1.5 text-on-surface-variant">{r.d}</td>
                        <td className="px-3 py-1.5 text-on-surface tabular-nums" dir="ltr">{r.a}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
      <p className="text-[11px] text-on-surface-variant text-center mt-3">مثال بأرقام تجريبية</p>
    </div>
  );
}

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
    <div className="min-h-screen bg-surface-container-lowest overflow-x-hidden font-sans text-on-surface" dir="rtl">
      <Navbar />

      {/* ── HERO ───────────────────────────────────────────────────────────── */}
      <section className="pt-28 pb-20 md:pt-36 md:pb-28">
        <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-14 items-center">
          <div>
            <p className="text-sm font-semibold text-primary mb-5">نظام إدارة متكامل للتاجر المصري</p>
            <h1 className="text-4xl md:text-6xl font-black leading-[1.15] tracking-tight mb-6">
              المرجع الرقمي
              <br />
              <span className="text-primary">للتاجر المصري</span>
            </h1>
            <p className="text-lg md:text-xl text-on-surface-variant leading-relaxed max-w-xl mb-9">
              المحاسبة والمبيعات والمخزون والموارد البشرية في مكان واحد. واسأل المساعد بالعربي عن أي تقرير، وحمّله Excel أو PDF في ثواني.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 mb-6">
              <Link href="/register" className="inline-flex items-center justify-center gap-2 bg-primary text-on-primary font-bold text-base px-8 py-3.5 rounded-xl hover:bg-primary-container transition-colors">
                ابدأ مجانًا
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <a href="#ai" className="inline-flex items-center justify-center gap-2 border border-outline-variant text-on-surface font-semibold text-base px-8 py-3.5 rounded-xl hover:bg-surface-container transition-colors">
                شوف المساعد الذكي
              </a>
            </div>
            <p className="text-sm text-on-surface-variant flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-primary" />
              بدون بطاقة ائتمان
            </p>
          </div>

          <ProductPreview />
        </div>
      </section>

      {/* ── FACTS ──────────────────────────────────────────────────────────── */}
      <section className="border-y border-outline-variant bg-surface-container-low">
        <div className="max-w-7xl mx-auto px-6 py-8 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {facts.map((f) => (
            <div key={f.label}>
              <p className="text-xl md:text-2xl font-black text-on-surface" dir="auto">{f.value}</p>
              <p className="text-sm text-on-surface-variant mt-1">{f.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── MODULES ────────────────────────────────────────────────────────── */}
      <section id="modules" className="py-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="max-w-2xl mb-14">
            <h2 className="text-3xl md:text-4xl font-black mb-4">كل اللي تجارتك محتاجاه، وحدات تضيفها وقت ما تحتاج</h2>
            <p className="text-lg text-on-surface-variant">ابدأ بالأساسيات، وزوّد لما تكبر. بدون تعقيدات.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {modules.map((mod) => (
              <div key={mod.title} className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-5 hover:border-primary/40 hover:shadow-md transition-all">
                <div className="flex items-start justify-between mb-4">
                  <div className="w-11 h-11 rounded-xl bg-primary-fixed text-primary flex items-center justify-center">
                    <mod.icon className="w-5 h-5" />
                  </div>
                  {mod.badge && <span className="text-[11px] font-bold bg-primary-fixed text-primary px-2 py-0.5 rounded-full">{mod.badge}</span>}
                </div>
                <h3 className="font-bold mb-1.5">{mod.title}</h3>
                <p className="text-sm text-on-surface-variant leading-relaxed">{mod.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── AI ─────────────────────────────────────────────────────────────── */}
      <section id="ai" className="py-24 bg-surface-container-low">
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
      <section id="pricing" className="py-24 bg-surface-container-low">
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
