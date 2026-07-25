"use client";

import Link from "next/link";
import {
  motion,
  useInView,
  useScroll,
  useTransform,
  AnimatePresence,
} from "framer-motion";
import {
  Package,
  BookOpen,
  Truck,
  Building2,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ArrowLeft,
  ChevronDown,
  BarChart3,
  Zap,
  Menu,
  X,
} from "lucide-react";
import { useRef, useState, useEffect } from "react";

// ─── Animation Variants ────────────────────────────────────────────────────────

const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  visible: (delay = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.65, ease: [0.22, 1, 0.36, 1] as any, delay },
  }),
};

const fadeIn = {
  hidden: { opacity: 0 },
  visible: (delay = 0) => ({
    opacity: 1,
    transition: { duration: 0.5, delay },
  }),
};

const staggerContainer = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.12, delayChildren: 0.1 },
  },
};

const cardVariant = {
  hidden: { opacity: 0, y: 28, scale: 0.97 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] as any },
  },
};

// ─── Navbar ────────────────────────────────────────────────────────────────────

function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.nav
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] as any }}
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-[#040D1B]/95 backdrop-blur-md border-b border-white/10 shadow-xl"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Logo — right side in RTL */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#FF9800] flex items-center justify-center shadow-lg shadow-[#FF9800]/30">
            <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-bold text-white text-[17px] tracking-tight">
            Trust Core
          </span>
          <span className="hidden sm:block text-[11px] text-[#BEC7DB] border border-white/15 rounded px-1.5 py-0.5">
            ERP
          </span>
        </div>

        {/* Desktop Actions */}
        <div className="hidden sm:flex items-center gap-3">
          <Link
            href="/login"
            className="text-[#BEC7DB] hover:text-white text-[14px] font-medium transition-colors px-3 py-1.5"
          >
            تسجيل الدخول
          </Link>
          <Link
            href="/register"
            className="bg-[#FF9800] hover:bg-[#E6890A] text-white text-[14px] font-semibold px-4 py-2 rounded-lg transition-all duration-200 shadow-lg shadow-[#FF9800]/25 hover:shadow-[#FF9800]/40 hover:scale-[1.02] active:scale-[0.98]"
          >
            ابدأ مجاناً
          </Link>
        </div>

        {/* Mobile menu toggle */}
        <button
          className="sm:hidden text-white p-1"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="القائمة"
        >
          {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile dropdown */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="sm:hidden bg-[#040D1B]/97 backdrop-blur-md border-t border-white/10 overflow-hidden"
          >
            <div className="px-4 py-4 flex flex-col gap-3">
              <Link
                href="/login"
                className="text-[#BEC7DB] text-[15px] py-2 hover:text-white transition-colors"
                onClick={() => setMenuOpen(false)}
              >
                تسجيل الدخول
              </Link>
              <Link
                href="/register"
                className="bg-[#FF9800] text-white text-[15px] font-semibold px-4 py-2.5 rounded-lg text-center"
                onClick={() => setMenuOpen(false)}
              >
                ابدأ مجاناً
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
}

// ─── Hero Section ──────────────────────────────────────────────────────────────

function HeroSection() {
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 500], [0, -80]);
  const opacity = useTransform(scrollY, [0, 400], [1, 0.3]);

  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden bg-[#040D1B] px-4 text-center">
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-[#FF9800]/8 rounded-full blur-[120px]" />
        <div className="absolute top-1/3 left-1/4 w-[300px] h-[300px] bg-[#FF9800]/5 rounded-full blur-[80px]" />
        {/* Grid overlay */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `linear-gradient(rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px)`,
            backgroundSize: "60px 60px",
          }}
        />
      </div>

      <motion.div style={{ y, opacity }} className="relative z-10 max-w-4xl">
        {/* Badge */}
        <motion.div
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          custom={0}
          className="inline-flex items-center gap-2 bg-[#FF9800]/12 border border-[#FF9800]/30 text-[#FF9800] text-[12px] font-semibold px-4 py-1.5 rounded-full mb-8"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          شبكة الثقة للتجار المصريين
        </motion.div>

        {/* Headline */}
        <motion.h1
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          custom={0.1}
          className="text-[clamp(2.2rem,5.5vw,4rem)] font-bold text-white leading-[1.15] tracking-tight mb-6"
        >
          أوقف خسائر الإرجاع{" "}
          <span className="relative">
            <span className="text-[#FF9800]">قبل الشحن</span>
            <motion.span
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ delay: 0.7, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              className="absolute -bottom-1 left-0 right-0 h-[3px] bg-gradient-to-l from-[#FF9800]/0 via-[#FF9800] to-[#FF9800]/0 origin-right"
            />
          </span>
          {" "}واضبط محاسبتك تلقائياً
        </motion.h1>

        {/* Subheadline */}
        <motion.p
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          custom={0.2}
          className="text-[clamp(1rem,2vw,1.25rem)] text-[#BEC7DB] leading-relaxed max-w-2xl mx-auto mb-10"
        >
          نظام التشغيل الشامل للتجار والموزعين المصريين — إدارة مخزون، محاسبة
          مزدوجة تلقائية، وشبكة ثقة تكشف أرقام الهاتف الخطرة قبل شحن الطلبات.
        </motion.p>

        {/* CTAs */}
        <motion.div
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          custom={0.3}
          className="flex flex-col sm:flex-row items-center justify-center gap-3"
        >
          <Link
            href="/register"
            id="hero-cta-primary"
            className="group relative bg-[#FF9800] hover:bg-[#E6890A] text-white font-bold text-[16px] px-8 py-3.5 rounded-xl transition-all duration-200 shadow-xl shadow-[#FF9800]/30 hover:shadow-[#FF9800]/50 hover:scale-[1.03] active:scale-[0.97] flex items-center gap-2"
          >
            ابدأ مجاناً الآن
            <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
          </Link>
          <a
            href="#features"
            id="hero-cta-secondary"
            className="group text-[#BEC7DB] hover:text-white font-semibold text-[15px] px-6 py-3.5 rounded-xl border border-white/15 hover:border-white/30 transition-all duration-200 flex items-center gap-2 hover:bg-white/5"
          >
            استعرض المميزات
            <ChevronDown className="w-4 h-4 transition-transform group-hover:translate-y-0.5" />
          </a>
        </motion.div>

        {/* Trust signals */}
        <motion.div
          variants={fadeIn}
          initial="hidden"
          animate="visible"
          custom={0.5}
          className="mt-14 flex flex-wrap items-center justify-center gap-6 text-[12px] text-[#75777D]"
        >
          {["بدون بطاقة ائتمان", "نسخة تجريبية 14 يوم", "دعم عربي كامل", "تشفير بنكي SSL"].map(
            (t) => (
              <span key={t} className="flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-[#FF9800]/70" />
                {t}
              </span>
            )
          )}
        </motion.div>
      </motion.div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2 }}
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
      >
        <motion.div
          animate={{ y: [0, 8, 0] }}
          transition={{ repeat: Infinity, duration: 1.8, ease: "easeInOut" }}
          className="w-5 h-8 border-2 border-white/20 rounded-full flex justify-center pt-1.5"
        >
          <div className="w-1 h-2 bg-[#FF9800]/70 rounded-full" />
        </motion.div>
      </motion.div>
    </section>
  );
}

// ─── Trust Network / "Moat" Section ───────────────────────────────────────────

function TrustNetworkSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });

  const riskEntries = [
    { phone: "01xxxxxxxxx8", status: "safe", label: "موثوق — 12 طلب ناجح", color: "text-[#2E7D32]", bg: "bg-[#E8F5E9]", icon: CheckCircle2 },
    { phone: "01xxxxxxxxx4", status: "risky", label: "مخاطرة عالية — 3 مرتجعات", color: "text-[#BA1A1A]", bg: "bg-[#FFEBEE]", icon: XCircle },
    { phone: "01xxxxxxxxx1", status: "warning", label: "تحت المراقبة — طلب جديد", color: "text-[#F9A825]", bg: "bg-[#FFFDE7]", icon: AlertTriangle },
  ];

  return (
    <section ref={ref} className="relative py-24 bg-[#FCF8FA] overflow-hidden">
      {/* Decorative blob */}
      <div className="absolute top-0 left-0 w-96 h-96 bg-[#FF9800]/5 rounded-full blur-3xl -translate-x-1/2 -translate-y-1/2 pointer-events-none" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          {/* Text side */}
          <motion.div
            variants={staggerContainer}
            initial="hidden"
            animate={isInView ? "visible" : "hidden"}
          >
            <motion.span
              variants={fadeUp}
              className="inline-flex items-center gap-2 bg-[#FF9800]/10 text-[#FF9800] text-[12px] font-bold px-3 py-1.5 rounded-full mb-5"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              شبكة الثقة — الميزة الحصرية
            </motion.span>

            <motion.h2
              variants={fadeUp}
              className="text-[clamp(1.8rem,3.5vw,2.8rem)] font-bold text-[#040D1B] leading-[1.2] mb-5"
            >
              اعرف مَن تشحن له{" "}
              <span className="text-[#FF9800]">قبل أن تدفع</span>
            </motion.h2>

            <motion.p
              variants={fadeUp}
              className="text-[#45474C] text-[15px] leading-relaxed mb-8"
            >
              كل رقم هاتف في منظومة التجار يبني سجلاً تلقائياً من الطلبات
              والمرتجعات. قبل شحن أي طلب، يُظهر النظام{" "}
              <strong className="text-[#040D1B]">تصنيف الثقة الفوري</strong> لهذا
              الرقم — مما يقطع سلسلة خسائر COD من مصدرها.
            </motion.p>

            <motion.div variants={fadeUp} className="flex flex-col gap-3">
              {[
                "رصد تلقائي لأرقام الإرجاع عبر شبكة التجار",
                "تنبيهات لحظية قبل تأكيد الشحن",
                "تقارير خسائر COD مجمّعة شهرياً",
              ].map((item) => (
                <div key={item} className="flex items-start gap-3">
                  <div className="mt-0.5 w-5 h-5 rounded-full bg-[#FF9800]/12 flex items-center justify-center shrink-0">
                    <CheckCircle2 className="w-3 h-3 text-[#FF9800]" />
                  </div>
                  <span className="text-[#45474C] text-[14px]">{item}</span>
                </div>
              ))}
            </motion.div>
          </motion.div>

          {/* Visual card */}
          <motion.div
            initial={{ opacity: 0, x: -30, scale: 0.96 }}
            animate={isInView ? { opacity: 1, x: 0, scale: 1 } : {}}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
          >
            <div className="bg-white rounded-2xl border border-[#C5C6CC]/60 shadow-2xl shadow-[#040D1B]/8 overflow-hidden">
              {/* Header bar */}
              <div className="bg-[#040D1B] px-5 py-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-[#FF4444]" />
                  <div className="w-3 h-3 rounded-full bg-[#FF9800]" />
                  <div className="w-3 h-3 rounded-full bg-[#2E7D32]" />
                </div>
                <div className="flex items-center gap-2 text-[#BEC7DB] text-[12px]">
                  <ShieldCheck className="w-3.5 h-3.5 text-[#FF9800]" />
                  بوابة التحقق من الشحن
                </div>
                <div className="w-8" />
              </div>

              <div className="p-6">
                {/* Order summary */}
                <div className="bg-[#F6F3F4] rounded-xl p-4 mb-5">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[#75777D] text-[12px]">طلب رقم</span>
                    <span className="font-mono text-[12px] text-[#040D1B] font-semibold">#ORD-20240724</span>
                  </div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[#75777D] text-[12px]">القيمة</span>
                    <span className="font-mono text-[14px] text-[#040D1B] font-bold">3,450.00 ج.م</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[#75777D] text-[12px]">الدفع</span>
                    <span className="bg-[#FFFDE7] text-[#F9A825] text-[11px] font-semibold px-2 py-0.5 rounded-full">كاش عند الاستلام</span>
                  </div>
                </div>

                {/* Risk entries */}
                <div className="space-y-3">
                  <p className="text-[#75777D] text-[11px] font-semibold uppercase tracking-wide mb-2">فحص شبكة الثقة</p>
                  {riskEntries.map((entry, i) => {
                    const Icon = entry.icon;
                    return (
                      <motion.div
                        key={entry.phone}
                        initial={{ opacity: 0, x: 16 }}
                        animate={isInView ? { opacity: 1, x: 0 } : {}}
                        transition={{ delay: 0.4 + i * 0.12, duration: 0.4 }}
                        className="flex items-center justify-between p-3 bg-[#F6F3F4] rounded-xl border border-[#E4E2E3]"
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-8 h-8 ${entry.bg} rounded-lg flex items-center justify-center`}>
                            <Icon className={`w-4 h-4 ${entry.color}`} />
                          </div>
                          <div>
                            <p className="font-mono text-[13px] text-[#040D1B] font-semibold">{entry.phone}</p>
                            <p className={`text-[11px] ${entry.color} font-medium`}>{entry.label}</p>
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>

                {/* Action */}
                <div className="mt-5 grid grid-cols-2 gap-3">
                  <button className="bg-[#FFEBEE] text-[#BA1A1A] text-[13px] font-semibold py-2.5 rounded-lg hover:bg-[#FFCDD2] transition-colors">
                    تعليق الطلب
                  </button>
                  <button className="bg-[#FF9800] text-white text-[13px] font-semibold py-2.5 rounded-lg hover:bg-[#E6890A] transition-colors shadow-lg shadow-[#FF9800]/25">
                    تأكيد الشحن
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

// ─── Features Grid ─────────────────────────────────────────────────────────────

const features = [
  {
    icon: Building2,
    title: "ERP متعدد الشركات",
    desc: "أدر عدة كيانات تجارية من لوحة واحدة مع عزل كامل للبيانات وقاعدة بيانات منفصلة لكل مستأجر.",
    badge: "Multi-Tenant",
    color: "#3B82F6",
    bg: "#EFF6FF",
  },
  {
    icon: BookOpen,
    title: "محاسبة مزدوجة تلقائية",
    desc: "كل فاتورة وكل دفعة تولّد قيود محاسبية تلقائياً بنظام القيد المزدوج — صفر أخطاء يدوية.",
    badge: "Auto Journal",
    color: "#10B981",
    bg: "#ECFDF5",
  },
  {
    icon: Package,
    title: "مخزون وأوامر شراء",
    desc: "تتبع المخزون الفعلي والمتوقع، أنشئ أوامر شراء، وتلقَّ تنبيهات نقص المخزون فوراً.",
    badge: "Inventory",
    color: "#FF9800",
    bg: "#FFF3E0",
  },
  {
    icon: Truck,
    title: "تتبع الشحن الفوري",
    desc: "ربط مباشر مع شركات الشحن المصرية — تتبع كل طلب من المستودع حتى باب العميل.",
    badge: "Shipping",
    color: "#8B5CF6",
    bg: "#F5F3FF",
  },
];

function FeaturesSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <section id="features" ref={ref} className="py-24 bg-[#040D1B] relative overflow-hidden">
      {/* ambient glows */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-[#FF9800]/6 rounded-full blur-[80px]" />
        <div className="absolute top-1/2 left-0 w-64 h-64 bg-[#3B82F6]/5 rounded-full blur-[60px]" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 relative z-10">
        {/* Section header */}
        <motion.div
          initial="hidden"
          animate={isInView ? "visible" : "hidden"}
          variants={staggerContainer}
          className="text-center mb-16"
        >
          <motion.span
            variants={fadeUp}
            className="inline-flex items-center gap-2 bg-[#FF9800]/12 border border-[#FF9800]/25 text-[#FF9800] text-[12px] font-bold px-3 py-1.5 rounded-full mb-5"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            كل ما تحتاجه في مكان واحد
          </motion.span>

          <motion.h2
            variants={fadeUp}
            className="text-[clamp(1.8rem,3.5vw,2.8rem)] font-bold text-white leading-tight mb-4"
          >
            منظومة متكاملة مصممة{" "}
            <span className="text-[#FF9800]">للتاجر المصري</span>
          </motion.h2>

          <motion.p
            variants={fadeUp}
            className="text-[#BEC7DB] text-[15px] max-w-xl mx-auto"
          >
            كل أداة مبنية على فهم عميق لتحديات التجارة المحلية والموزعين الكبار.
          </motion.p>
        </motion.div>

        {/* Cards grid */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate={isInView ? "visible" : "hidden"}
          className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5"
        >
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.title}
                variants={cardVariant}
                whileHover={{ y: -6, transition: { duration: 0.25 } }}
                className="group bg-[#1B1B1D] hover:bg-[#242428] border border-white/8 hover:border-[#FF9800]/25 rounded-2xl p-6 cursor-default transition-colors duration-300 relative overflow-hidden"
              >
                {/* Card glow on hover */}
                <div
                  className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-2xl pointer-events-none"
                  style={{
                    background: `radial-gradient(circle at 50% 0%, ${f.color}10 0%, transparent 70%)`,
                  }}
                />

                <div
                  className="w-11 h-11 rounded-xl flex items-center justify-center mb-4 shadow-lg"
                  style={{ backgroundColor: f.bg }}
                >
                  <Icon className="w-5 h-5" style={{ color: f.color }} />
                </div>

                <div
                  className="text-[10px] font-bold tracking-widest uppercase mb-3 px-2 py-0.5 rounded-full inline-block"
                  style={{ color: f.color, backgroundColor: f.bg }}
                >
                  {f.badge}
                </div>

                <h3 className="text-white font-bold text-[15px] mb-2.5 leading-snug">
                  {f.title}
                </h3>
                <p className="text-[#75777D] group-hover:text-[#BEC7DB] text-[13px] leading-relaxed transition-colors duration-300">
                  {f.desc}
                </p>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}

// ─── Social Proof Strip ────────────────────────────────────────────────────────

function SocialProofSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });

  const stats = [
    { value: "12,000+", label: "طلب يومي تحت الإدارة" },
    { value: "98.4%", label: "دقة القيود المحاسبية" },
    { value: "35%", label: "انخفاض في مرتجعات COD" },
    { value: "< 2 ث", label: "زمن استجابة API" },
  ];

  return (
    <section ref={ref} className="py-16 bg-[#FCF8FA] border-y border-[#C5C6CC]/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate={isInView ? "visible" : "hidden"}
          className="grid grid-cols-2 lg:grid-cols-4 gap-8"
        >
          {stats.map((s) => (
            <motion.div
              key={s.label}
              variants={cardVariant}
              className="text-center"
            >
              <div className="text-[clamp(1.8rem,4vw,2.8rem)] font-bold text-[#FF9800] font-mono leading-none mb-2">
                {s.value}
              </div>
              <div className="text-[#75777D] text-[13px]">{s.label}</div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

// ─── Final CTA Band ────────────────────────────────────────────────────────────

function CTABand() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-40px" });

  return (
    <section
      ref={ref}
      className="relative py-24 bg-gradient-to-b from-[#040D1B] to-[#0A1628] overflow-hidden"
    >
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-[#FF9800]/8 rounded-full blur-[100px]" />
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 text-center relative z-10">
        <motion.div
          initial="hidden"
          animate={isInView ? "visible" : "hidden"}
          variants={staggerContainer}
        >
          <motion.h2
            variants={fadeUp}
            className="text-[clamp(1.8rem,4vw,3rem)] font-bold text-white leading-tight mb-4"
          >
            جاهز تبدأ تحكم في تجارتك؟
          </motion.h2>
          <motion.p
            variants={fadeUp}
            className="text-[#BEC7DB] text-[16px] mb-10"
          >
            انضم لآلاف التجار الذين يديرون مخزونهم ومحاسبتهم من مكان واحد.
          </motion.p>
          <motion.div
            variants={fadeUp}
            className="flex flex-col sm:flex-row items-center justify-center gap-4"
          >
            <Link
              href="/register"
              id="cta-band-register"
              className="group bg-[#FF9800] hover:bg-[#E6890A] text-white font-bold text-[16px] px-10 py-4 rounded-xl transition-all duration-200 shadow-2xl shadow-[#FF9800]/30 hover:shadow-[#FF9800]/50 hover:scale-[1.03] active:scale-[0.97] flex items-center gap-2"
            >
              ابدأ مجاناً — 14 يوم تجريبي
              <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
            </Link>
            <Link
              href="/login"
              id="cta-band-login"
              className="text-[#BEC7DB] hover:text-white font-semibold text-[15px] px-6 py-4 rounded-xl border border-white/15 hover:border-white/30 transition-all duration-200 hover:bg-white/5"
            >
              لدي حساب بالفعل
            </Link>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

// ─── Footer ────────────────────────────────────────────────────────────────────

function Footer() {
  const links = {
    المنتج: [
      { label: "المميزات", href: "#features" },
      { label: "الأسعار", href: "#" },
      { label: "التوثيق", href: "#" },
      { label: "قائمة الانتظار", href: "/register" },
    ],
    الشركة: [
      { label: "من نحن", href: "#" },
      { label: "المدونة", href: "#" },
      { label: "التوظيف", href: "#" },
      { label: "تواصل معنا", href: "#" },
    ],
    قانوني: [
      { label: "سياسة الخصوصية", href: "/privacy" },
      { label: "الشروط والأحكام", href: "/terms" },
    ],
  };

  return (
    <footer className="bg-[#040D1B] border-t border-white/8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-14">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-10 mb-12">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-8 h-8 rounded-lg bg-[#FF9800] flex items-center justify-center shadow-lg shadow-[#FF9800]/30">
                <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
              </div>
              <span className="font-bold text-white text-[16px]">Trust Core ERP</span>
            </div>
            <p className="text-[#75777D] text-[13px] leading-relaxed max-w-xs">
              نظام إدارة الأعمال الأكثر شمولاً للتجار والموزعين في مصر.
            </p>
          </div>

          {/* Links */}
          {Object.entries(links).map(([group, items]) => (
            <div key={group}>
              <h4 className="text-white font-semibold text-[13px] mb-4">{group}</h4>
              <ul className="space-y-2.5">
                {items.map((item) => (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      className="text-[#75777D] hover:text-[#FF9800] text-[13px] transition-colors duration-150"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="border-t border-white/8 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-[#75777D] text-[12px]">
            © {new Date().getFullYear()} Trust Core ERP. جميع الحقوق محفوظة.
          </p>
          <div className="flex items-center gap-1 text-[#75777D] text-[12px]">
            <span>صُنع بـ</span>
            <span className="text-[#FF9800]">♥</span>
            <span>في مصر</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

// ─── Page Assembly ─────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <main className="min-h-screen font-sans">
      <Navbar />
      <HeroSection />
      <SocialProofSection />
      <TrustNetworkSection />
      <FeaturesSection />
      <CTABand />
      <Footer />
    </main>
  );
}
