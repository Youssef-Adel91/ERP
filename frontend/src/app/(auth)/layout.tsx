import type { Metadata } from 'next';
import Link from 'next/link';
import { Zap, ShieldCheck, BarChart3, Package } from 'lucide-react';

export const metadata: Metadata = {
  title: 'التحقق من الهوية | Trust Core ERP',
  description: 'سجّل دخولك أو أنشئ حساباً جديداً لإدارة تجارتك مع Trust Core ERP.',
};

const trustPoints = [
  {
    icon: ShieldCheck,
    title: 'شبكة الثقة الحصرية',
    desc: 'افحص أي رقم هاتف قبل الشحن لتصفير خسائر الإرجاع.',
  },
  {
    icon: BarChart3,
    title: 'محاسبة مزدوجة تلقائية',
    desc: 'كل فاتورة تولّد قيوداً محاسبية صحيحة بدون تدخل يدوي.',
  },
  {
    icon: Package,
    title: 'مخزون وموردون في مكان واحد',
    desc: 'أوامر شراء، تنبيهات نقص، وتتبع شحنات لحظي.',
  },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex bg-[#040D1B]">
      {/* ── Left brand panel (hidden on mobile) ──────────────────────────── */}
      <div className="hidden lg:flex lg:w-[46%] xl:w-[42%] flex-col justify-between p-12 relative overflow-hidden shrink-0">
        {/* Ambient glows */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[400px] bg-[#FF9800]/10 rounded-full blur-[100px]" />
          <div className="absolute bottom-1/4 right-0 w-[300px] h-[300px] bg-[#3B82F6]/6 rounded-full blur-[80px]" />
          {/* Subtle grid */}
          <div
            className="absolute inset-0 opacity-[0.035]"
            style={{
              backgroundImage: `linear-gradient(rgba(255,255,255,0.4) 1px, transparent 1px),
                                linear-gradient(90deg, rgba(255,255,255,0.4) 1px, transparent 1px)`,
              backgroundSize: '50px 50px',
            }}
          />
        </div>

        {/* Logo */}
        <div className="relative z-10">
          <Link href="/" className="inline-flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl bg-[#FF9800] flex items-center justify-center shadow-xl shadow-[#FF9800]/30 group-hover:scale-105 transition-transform">
              <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
            </div>
            <div>
              <p className="text-white font-bold text-[17px] leading-none">Trust Core</p>
              <p className="text-[#BEC7DB] text-[11px] font-medium mt-0.5">ERP Platform</p>
            </div>
          </Link>
        </div>

        {/* Headline */}
        <div className="relative z-10 flex-1 flex flex-col justify-center py-16">
          <p className="text-[#FF9800] text-[13px] font-bold tracking-widest uppercase mb-4">
            للتجار والموزعين المصريين
          </p>
          <h1 className="text-[clamp(1.9rem,2.8vw,2.6rem)] font-bold text-white leading-[1.2] mb-6">
            نظام التشغيل الكامل
            <br />
            <span className="text-[#FF9800]">لتجارتك</span>
          </h1>
          <p className="text-[#BEC7DB] text-[15px] leading-relaxed mb-12 max-w-sm">
            مخزون، محاسبة، شحن، وشبكة ثقة — كل شيء في مكان واحد.
          </p>

          {/* Trust points */}
          <div className="flex flex-col gap-5">
            {trustPoints.map((p) => {
              const Icon = p.icon;
              return (
                <div key={p.title} className="flex items-start gap-4">
                  <div className="w-9 h-9 rounded-xl bg-[#FF9800]/12 border border-[#FF9800]/20 flex items-center justify-center shrink-0 mt-0.5">
                    <Icon className="w-4 h-4 text-[#FF9800]" />
                  </div>
                  <div>
                    <p className="text-white font-semibold text-[14px] mb-0.5">{p.title}</p>
                    <p className="text-[#75777D] text-[13px] leading-relaxed">{p.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer quote */}
        <div className="relative z-10 border-t border-white/8 pt-6">
          <p className="text-[#45474C] text-[12px] leading-relaxed">
            "انضم لآلاف التجار الذين يديرون مخزونهم ومحاسبتهم بدون صداع."
          </p>
          <p className="text-[#FF9800] text-[11px] font-semibold mt-1">
            — فريق Trust Core ERP
          </p>
        </div>
      </div>

      {/* ── Right form panel ──────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col bg-[#FCF8FA] overflow-y-auto">
        {/* Mobile logo */}
        <div className="lg:hidden flex items-center justify-center pt-8 pb-4">
          <Link href="/" className="inline-flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#FF9800] flex items-center justify-center shadow-lg shadow-[#FF9800]/30">
              <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
            </div>
            <span className="font-bold text-[#040D1B] text-[16px]">Trust Core ERP</span>
          </Link>
        </div>

        <div className="flex-1 flex flex-col justify-center px-6 py-10 sm:px-10 lg:px-16 xl:px-20">
          {children}
        </div>

        <div className="py-6 text-center text-[11px] text-[#75777D]">
          © {new Date().getFullYear()} Trust Core ERP — جميع الحقوق محفوظة
        </div>
      </div>
    </div>
  );
}
