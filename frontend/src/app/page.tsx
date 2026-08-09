"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Wallet, TrendingUp, Package, Users, Truck, Plane, Coffee, Car,
  ShieldCheck, Zap, Brain, BarChart3, MessageSquareText, ArrowLeft,
  CheckCircle2, Star, Play, ChevronDown, Globe, Phone, Mail,
  LayoutDashboard, Receipt, Store, Building2, CreditCard, PackageCheck,
  Megaphone, BotMessageSquare, LineChart, Search, Lock, Sparkles,
} from "lucide-react";

// ── Animated Counter ──────────────────────────────────────────────────────────
function Counter({ to, suffix = "", prefix = "" }: { to: number; suffix?: string; prefix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      let start = 0;
      const step = Math.ceil(to / 60);
      const timer = setInterval(() => {
        start = Math.min(start + step, to);
        setCount(start);
        if (start >= to) clearInterval(timer);
      }, 20);
    }, { threshold: 0.5 });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [to]);
  return <span ref={ref}>{prefix}{count.toLocaleString("ar-EG")}{suffix}</span>;
}

// ── Data ──────────────────────────────────────────────────────────────────────
const modules = [
  { icon: Wallet,         title: "المحاسبة والمالية",         desc: "دفتر أستاذ، توازن تلقائي، وتقارير مالية لحظية.", badge: "الأكثر طلباً", color: "from-blue-600 to-blue-800" },
  { icon: Receipt,        title: "الفاتورة الإلكترونية",      desc: "متوافق 100% مع منظومة مصلحة الضرائب المصرية.", badge: "ETA متوافق", color: "from-emerald-600 to-emerald-800" },
  { icon: TrendingUp,     title: "المبيعات وعروض الأسعار",    desc: "إدارة العملاء، العروض، الفواتير وقنوات البيع.", badge: null, color: "from-violet-600 to-violet-800" },
  { icon: Store,          title: "نقاط البيع (POS)",           desc: "واجهة سريعة للكاشير مع دعم الباركود والطابعات.", badge: "جديد", color: "from-orange-600 to-orange-800" },
  { icon: Package,        title: "المخزون والمستودعات",        desc: "تتبع الأصناف، المخازن المتعددة وأوامر الشراء.", badge: null, color: "from-cyan-600 to-cyan-800" },
  { icon: Users,          title: "الموارد البشرية",            desc: "التوظيف، الرواتب، الحضور والتأمينات الاجتماعية.", badge: null, color: "from-pink-600 to-pink-800" },
  { icon: PackageCheck,   title: "الشحن والتوصيل",             desc: "ربط شركات الشحن المحلية وتتبع الطلبات لحظياً.", badge: null, color: "from-teal-600 to-teal-800" },
  { icon: Building2,      title: "إدارة الفروع",               desc: "لوحة مركزية تحكم فيها جميع فروعك من مكان واحد.", badge: null, color: "from-indigo-600 to-indigo-800" },
  { icon: Plane,          title: "السياحة والسفر",             desc: "حجوزات الطيران، الفنادق ومتابعة ملفات العملاء.", badge: null, color: "from-sky-600 to-sky-800" },
  { icon: Coffee,         title: "المطاعم والضيافة",           desc: "منيو رقمي، إدارة الطاولات ونقاط بيع سريعة.", badge: null, color: "from-amber-600 to-amber-800" },
  { icon: Car,            title: "تأجير السيارات",             desc: "إدارة الأسطول، العقود وتتبع الصيانة الدورية.", badge: null, color: "from-red-600 to-red-800" },
  { icon: CreditCard,     title: "الاشتراك والفوترة",          desc: "إدارة خطط الاشتراك وفواتير العملاء تلقائياً.", badge: null, color: "from-purple-600 to-purple-800" },
];

const aiFeatures = [
  { icon: LineChart,         title: "تحليل مالي ذكي",       desc: "توقع التدفق النقدي واكتشاف الشذوذات المالية تلقائياً بالذكاء الاصطناعي." },
  { icon: BotMessageSquare,  title: "مساعد عربي بالـ AI",   desc: "اسأل المساعد بالعربية عن أي تقرير أو بيانات وهو يجيبك فوراً." },
  { icon: Search,            title: "كشف الغش والأخطاء",    desc: "يراقب كل العمليات ويبعتلك تنبيه لو في حاجة غير طبيعية." },
  { icon: Megaphone,         title: "توقع المبيعات",         desc: "خوارزميات ML بتتوقعلك المبيعات للشهر القادم بدقة عالية." },
];

const testimonials = [
  { name: "أحمد الشناوي", role: "مدير مالي تنفيذي", company: "شركة النصر للتجارة", text: "وفّرنا 40% من وقت الفريق المالي بعد ما طبّقنا Nexus ERP. الفواتير الإلكترونية بقت تتعمل تلقائي بالكامل.", rating: 5 },
  { name: "منى إبراهيم",  role: "مديرة العمليات",   company: "مجموعة الدلتا للمقاولات", text: "الداشبورد بيدّيني نظرة كاملة على كل الفروع في ثواني. ما كانتش عندنا رؤية كده قبل كده.", rating: 5 },
  { name: "خالد محمود",   role: "صاحب مشروع",       company: "متاجر الحرية - 12 فرع", text: "بدأت بفرع واحد وعدّيت على 12 فرع من غير ما أحتاج أشتري سوفت وير جديد. الـ pricing عادل جداً.", rating: 5 },
];

const stats = [
  { value: 1200, suffix: "+", label: "عميل نشط" },
  { value: 19,   suffix: "+", label: "موديول متكامل" },
  { value: 99.9, suffix: "%", label: "uptime مضمون", isFloat: true },
  { value: 4,    suffix: " دول", label: "تشغيل فعلي" },
];

// ── Navbar ───────────────────────────────────────────────────────────────────
function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <header className={`fixed top-0 w-full z-50 transition-all duration-300 ${scrolled ? "bg-white/95 backdrop-blur-md shadow-sm border-b border-gray-100" : "bg-transparent"}`}>
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between" dir="rtl">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 bg-[#00288e] rounded-xl flex items-center justify-center shadow">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-white">
              <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z"/>
            </svg>
          </div>
          <span className={`font-bold text-lg tracking-tight ${scrolled ? "text-[#00288e]" : "text-white"}`}>Nexus ERP</span>
        </Link>

        <nav className={`hidden md:flex items-center gap-6 text-sm font-medium ${scrolled ? "text-gray-600" : "text-white/90"}`}>
          {[["الوحدات","#modules"],["الذكاء الاصطناعي","#ai"],["آراء العملاء","#testimonials"],["الأسعار","#pricing"]].map(([label, href]) => (
            <a key={href} href={href} className="hover:text-[#00288e] transition-colors">{label}</a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <Link href="/login" className={`hidden sm:block text-sm font-semibold px-4 py-1.5 rounded-lg transition-all ${scrolled ? "text-[#00288e] hover:bg-blue-50" : "text-white hover:bg-white/10"}`}>
            تسجيل الدخول
          </Link>
          <Link href="/register" className="bg-[#00288e] text-white text-sm font-bold px-5 py-2 rounded-lg hover:bg-[#001f6e] transition-all shadow hover:shadow-md active:scale-95">
            ابدأ مجاناً ←
          </Link>
        </div>
      </div>
    </header>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white overflow-x-hidden font-sans" dir="rtl">
      <Navbar />

      {/* ── HERO ───────────────────────────────────────────────────────────── */}
      <section className="relative min-h-screen flex items-center justify-center text-center overflow-hidden">
        {/* Background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#00288e] via-[#0a1f6b] to-[#440098]" />
        {/* Grid overlay */}
        <div className="absolute inset-0 opacity-10"
          style={{ backgroundImage: "linear-gradient(rgba(255,255,255,.1) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.1) 1px,transparent 1px)", backgroundSize: "60px 60px" }} />
        {/* Blobs */}
        <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 left-1/3 w-80 h-80 bg-purple-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }} />

        <div className="relative z-10 max-w-5xl mx-auto px-6 pt-24 pb-16">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 text-white/90 px-4 py-1.5 rounded-full text-sm font-medium mb-8 backdrop-blur-sm">
            <Sparkles className="w-4 h-4 text-yellow-400" />
            <span>مدعوم بالذكاء الاصطناعي — مصنوع للسوق المصري</span>
          </div>

          <h1 className="text-5xl md:text-7xl font-black text-white leading-tight mb-6 tracking-tight">
            المرجع الرقمي
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-l from-yellow-300 to-orange-300">
              للتاجر المصري
            </span>
          </h1>

          <p className="text-xl md:text-2xl text-white/80 max-w-3xl mx-auto mb-10 leading-relaxed">
            منصة SaaS متكاملة تجمع كل اللي محتاجه تجارتك —
            <strong className="text-white"> محاسبة، مبيعات، مخزون، HR، الفاتورة الإلكترونية </strong>
            وأكتر من 19 نظام — كلهم في مكان واحد بقوة الـ AI.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-16">
            <Link href="/register"
              className="bg-white text-[#00288e] font-black text-lg px-10 py-4 rounded-xl hover:shadow-2xl hover:scale-105 transition-all duration-200 flex items-center justify-center gap-2">
              ابدأ مجاناً الآن
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <a href="#modules"
              className="border-2 border-white/40 text-white font-bold text-lg px-8 py-4 rounded-xl hover:bg-white/10 transition-all flex items-center justify-center gap-2">
              <Play className="w-5 h-5" />
              شوف كيف يشتغل
            </a>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-3xl mx-auto">
            {stats.map((s) => (
              <div key={s.label} className="bg-white/10 backdrop-blur border border-white/20 rounded-2xl p-4">
                <div className="text-3xl font-black text-white mb-1">
                  {s.isFloat
                    ? <span>{s.value}{s.suffix}</span>
                    : <Counter to={s.value as number} suffix={s.suffix} />
                  }
                </div>
                <div className="text-white/70 text-sm">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Scroll hint */}
        <a href="#modules" className="absolute bottom-8 left-1/2 -translate-x-1/2 text-white/50 hover:text-white/80 transition-colors animate-bounce">
          <ChevronDown className="w-8 h-8" />
        </a>
      </section>

      {/* ── MODULES MARKETPLACE ─────────────────────────────────────────────── */}
      <section id="modules" className="py-24 bg-gray-50">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 bg-blue-50 text-[#00288e] px-4 py-1.5 rounded-full text-sm font-bold mb-4">
              <Store className="w-4 h-4" />
              Marketplace الأنظمة
            </div>
            <h2 className="text-4xl md:text-5xl font-black text-gray-900 mb-4">
              كل اللي محتاجه <span className="text-[#00288e]">في مكان واحد</span>
            </h2>
            <p className="text-xl text-gray-500 max-w-2xl mx-auto">
              اشترك في الأنظمة اللي تحتاجها بس — وزود لما تكبر. بدون تعقيدات.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {modules.map((mod) => (
              <div key={mod.title}
                className="group bg-white rounded-2xl border border-gray-100 p-5 hover:shadow-xl hover:-translate-y-1 transition-all duration-200 cursor-pointer">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${mod.color} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform shadow`}>
                  <mod.icon className="w-6 h-6 text-white" />
                </div>
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-bold text-gray-900 text-base leading-tight">{mod.title}</h3>
                  {mod.badge && (
                    <span className="text-[10px] font-bold bg-[#00288e]/10 text-[#00288e] px-2 py-0.5 rounded-full whitespace-nowrap mr-1">
                      {mod.badge}
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-500 leading-relaxed">{mod.desc}</p>
                <div className="mt-4 flex items-center gap-1 text-[#00288e] text-sm font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                  <span>اعرف أكتر</span>
                  <ArrowLeft className="w-3.5 h-3.5" />
                </div>
              </div>
            ))}
          </div>

          <div className="text-center mt-12">
            <Link href="/register"
              className="inline-flex items-center gap-2 bg-[#00288e] text-white font-bold text-lg px-10 py-4 rounded-xl hover:bg-[#001f6e] transition-all shadow-lg hover:shadow-xl active:scale-95">
              ابدأ تجربتك المجانية
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <p className="text-gray-400 text-sm mt-3">لا بطاقة ائتمانية — 14 يوم مجاناً</p>
          </div>
        </div>
      </section>

      {/* ── AI SECTION ──────────────────────────────────────────────────────── */}
      <section id="ai" className="py-24 bg-gradient-to-br from-[#00288e] to-[#440098] overflow-hidden relative">
        <div className="absolute inset-0 opacity-5"
          style={{ backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)", backgroundSize: "40px 40px" }} />

        <div className="relative max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 text-white px-4 py-1.5 rounded-full text-sm font-bold mb-4">
              <Brain className="w-4 h-4 text-yellow-400" />
              الذكاء الاصطناعي
            </div>
            <h2 className="text-4xl md:text-5xl font-black text-white mb-4">
              مش بس نظام ERP —<br />
              <span className="text-yellow-300">مساعد ذكي بالعربي</span>
            </h2>
            <p className="text-xl text-white/70 max-w-2xl mx-auto">
              خدمات الذكاء الاصطناعي مدمجة في كل وحدة عشان تساعدك تاخد قرارات أسرع وأذكى.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {aiFeatures.map((f) => (
              <div key={f.title}
                className="bg-white/10 backdrop-blur border border-white/20 rounded-2xl p-6 hover:bg-white/15 transition-all group">
                <div className="w-12 h-12 bg-yellow-400/20 rounded-xl flex items-center justify-center mb-4 group-hover:bg-yellow-400/30 transition-colors">
                  <f.icon className="w-6 h-6 text-yellow-300" />
                </div>
                <h3 className="text-xl font-bold text-white mb-2">{f.title}</h3>
                <p className="text-white/70 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>

          {/* AI Demo Card */}
          <div className="mt-12 bg-white/10 backdrop-blur border border-white/20 rounded-3xl p-8 max-w-2xl mx-auto">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-full bg-yellow-400 flex items-center justify-center">
                <BotMessageSquare className="w-5 h-5 text-gray-900" />
              </div>
              <div>
                <p className="font-bold text-white">مساعد Nexus</p>
                <p className="text-white/50 text-xs">متصل الآن</p>
              </div>
              <span className="mr-auto w-2 h-2 bg-green-400 rounded-full" />
            </div>
            <div className="space-y-3 text-sm">
              <div className="bg-white/10 rounded-2xl rounded-tl-none p-3 text-white/90 max-w-xs">
                إيه المنتج الأكتر مبيعاً الشهر ده؟
              </div>
              <div className="bg-yellow-400 rounded-2xl rounded-tr-none p-3 text-gray-900 font-medium max-w-xs mr-auto text-left" dir="rtl">
                🏆 المنتج الأعلى مبيعاً هو <strong>"كابل USB-C"</strong> بـ 1,240 وحدة — زيادة 18% عن الشهر اللي فات.
              </div>
              <div className="bg-white/10 rounded-2xl rounded-tl-none p-3 text-white/90 max-w-xs">
                وإيه توقعك للشهر الجاي؟
              </div>
              <div className="flex items-center gap-2 text-white/40 text-xs">
                <span className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-white/40 rounded-full animate-bounce" />
                  <span className="w-1.5 h-1.5 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: "0.15s" }} />
                  <span className="w-1.5 h-1.5 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: "0.3s" }} />
                </span>
                Nexus AI بيفكر...
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── TESTIMONIALS ────────────────────────────────────────────────────── */}
      <section id="testimonials" className="py-24 bg-white">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 bg-green-50 text-green-700 px-4 py-1.5 rounded-full text-sm font-bold mb-4">
              <CheckCircle2 className="w-4 h-4" />
              قصص نجاح حقيقية
            </div>
            <h2 className="text-4xl md:text-5xl font-black text-gray-900 mb-4">
              بيقولوا عنّا إيه؟
            </h2>
            <p className="text-xl text-gray-500">آراء من شركات مصرية فعلاً بتستخدم Nexus ERP</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {testimonials.map((t) => (
              <div key={t.name} className="bg-gray-50 rounded-2xl p-6 border border-gray-100 hover:shadow-lg transition-shadow">
                <div className="flex gap-0.5 mb-4">
                  {Array.from({ length: t.rating }).map((_, i) => (
                    <Star key={i} className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 leading-relaxed mb-6 text-sm">"{t.text}"</p>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#00288e] to-[#440098] flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                    {t.name[0]}
                  </div>
                  <div>
                    <p className="font-bold text-gray-900 text-sm">{t.name}</p>
                    <p className="text-gray-500 text-xs">{t.role} · {t.company}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRICING TEASER ──────────────────────────────────────────────────── */}
      <section id="pricing" className="py-24 bg-gray-50">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-[#00288e] px-4 py-1.5 rounded-full text-sm font-bold mb-6">
            <CreditCard className="w-4 h-4" />
            التسعير
          </div>
          <h2 className="text-4xl md:text-5xl font-black text-gray-900 mb-4">
            ابدأ مجاناً —
            <span className="text-[#00288e]"> ادفع لما تكبر</span>
          </h2>
          <p className="text-xl text-gray-500 mb-12 max-w-2xl mx-auto">
            مفيش رسوم أولية. تدفع حسب الوحدات اللي بتستخدمها فعلاً. اشتراك شهري بسيط يبدأ من 299 ج.م / شهر.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            {[
              { name: "Starter", price: "299", desc: "لأصحاب المشاريع والمتاجر الصغيرة", features: ["5 مستخدمين", "3 وحدات", "10,000 فاتورة/شهر", "دعم عبر الواتساب"] },
              { name: "Business", price: "899", desc: "للشركات المتنامية", features: ["25 مستخدماً", "كل الوحدات", "فواتير غير محدودة", "AI تحليلات", "دعم أولوية"], popular: true },
              { name: "Enterprise", price: "مخصص", desc: "للمجموعات والشركات الكبرى", features: ["مستخدمين غير محدودين", "فروع غير محدودة", "تكامل مخصص", "مدير حساب مخصص", "SLA 99.9%"] },
            ].map((plan) => (
              <div key={plan.name}
                className={`relative rounded-2xl p-6 text-right border ${plan.popular ? "bg-[#00288e] border-transparent shadow-2xl scale-105 text-white" : "bg-white border-gray-100"}`}>
                {plan.popular && (
                  <div className="absolute -top-3 right-1/2 translate-x-1/2 bg-yellow-400 text-gray-900 text-xs font-black px-4 py-1 rounded-full whitespace-nowrap">
                    ⭐ الأكثر شعبية
                  </div>
                )}
                <h3 className={`font-black text-xl mb-1 ${plan.popular ? "text-white" : "text-gray-900"}`}>{plan.name}</h3>
                <p className={`text-sm mb-4 ${plan.popular ? "text-blue-200" : "text-gray-500"}`}>{plan.desc}</p>
                <div className={`text-3xl font-black mb-6 ${plan.popular ? "text-white" : "text-gray-900"}`}>
                  {plan.price === "مخصص" ? plan.price : <>{plan.price}<span className="text-base font-normal mr-1">ج.م / شهر</span></>}
                </div>
                <ul className="space-y-2 mb-6">
                  {plan.features.map((f) => (
                    <li key={f} className={`flex items-center gap-2 text-sm ${plan.popular ? "text-blue-100" : "text-gray-600"}`}>
                      <CheckCircle2 className={`w-4 h-4 flex-shrink-0 ${plan.popular ? "text-yellow-300" : "text-green-500"}`} />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/register"
                  className={`block w-full py-3 rounded-xl font-bold text-center transition-all ${plan.popular ? "bg-white text-[#00288e] hover:bg-blue-50" : "bg-[#00288e] text-white hover:bg-[#001f6e]"}`}>
                  ابدأ الآن
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA BANNER ──────────────────────────────────────────────────────── */}
      <section className="py-20 bg-gradient-to-l from-[#00288e] to-[#440098] relative overflow-hidden">
        <div className="absolute inset-0 opacity-10"
          style={{ backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)", backgroundSize: "32px 32px" }} />
        <div className="relative max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-4xl md:text-5xl font-black text-white mb-6">
            جاهز تبدأ رحلة الرقمنة؟
          </h2>
          <p className="text-xl text-white/80 mb-10 max-w-xl mx-auto">
            انضم لأكتر من 1,200 تاجر مصري بيديروا أعمالهم بذكاء مع Nexus ERP.
          </p>
          <Link href="/register"
            className="inline-flex items-center gap-3 bg-white text-[#00288e] font-black text-xl px-12 py-5 rounded-2xl hover:shadow-2xl hover:scale-105 transition-all duration-200">
            أنشئ حسابك المجاني
            <ArrowLeft className="w-6 h-6" />
          </Link>
          <p className="text-white/50 text-sm mt-4">بدون بطاقة ائتمان · 14 يوم تجربة مجانية · إلغاء في أي وقت</p>
        </div>
      </section>

      {/* ── FOOTER ──────────────────────────────────────────────────────────── */}
      <footer className="bg-gray-950 text-gray-400 py-12 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
            <div className="col-span-2 md:col-span-1">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 bg-[#00288e] rounded-lg flex items-center justify-center">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-4 h-4 fill-white">
                    <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z"/>
                  </svg>
                </div>
                <span className="font-bold text-white">Nexus ERP</span>
              </div>
              <p className="text-sm leading-relaxed">المرجع الرقمي للتاجر المصري — نظام إدارة متكامل مصنوع للسوق المصري.</p>
            </div>

            {[
              { title: "الأنظمة", links: ["المحاسبة", "المبيعات", "المخزون", "الموارد البشرية", "الفاتورة الإلكترونية"] },
              { title: "الشركة", links: ["عن Nexus", "المدونة", "الوظائف", "اتصل بنا"] },
              { title: "الدعم", links: ["مركز المساعدة", "الوثائق التقنية", "حالة الخدمة", "شروط الخصوصية"] },
            ].map((col) => (
              <div key={col.title}>
                <h4 className="text-white font-bold mb-4 text-sm">{col.title}</h4>
                <ul className="space-y-2">
                  {col.links.map((link) => (
                    <li key={link}><a href="#" className="text-sm hover:text-white transition-colors">{link}</a></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="border-t border-gray-800 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-sm">© {new Date().getFullYear()} Nexus ERP. جميع الحقوق محفوظة.</p>
            <div className="flex items-center gap-4 text-sm">
              <a href="mailto:youssefffadel555@gmail.com" className="flex items-center gap-1 hover:text-white transition-colors">
                <Mail className="w-3.5 h-3.5" />
                youssefffadel555@gmail.com
              </a>
              <div className="flex items-center gap-1">
                <Globe className="w-3.5 h-3.5" />
                مصر · السعودية · الإمارات · الكويت
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
