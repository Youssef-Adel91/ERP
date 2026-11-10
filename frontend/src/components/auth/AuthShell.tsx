import Image from "next/image";
import { ShieldCheck, BarChart3, Boxes, Sparkles } from "lucide-react";

const highlights = [
  { icon: Boxes, text: "اختار الأنظمة اللي محتاجها وزوّد غيرها وقت ما تكبر" },
  { icon: BarChart3, text: "تقارير مبيعات ومخزون ومحاسبة لحظية" },
  { icon: Sparkles, text: "اسأل المساعد بالعربي واستلم التقرير في ثواني" },
];

export default function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface grid lg:grid-cols-2">
      <div className="flex flex-col items-center justify-center p-6 lg:p-12">{children}</div>

      <aside className="hidden lg:flex flex-col justify-between bg-[#00071C] text-white p-12 relative isolate overflow-hidden">
        <Image src="/hero-bg.jpg" alt="" fill sizes="50vw" className="object-cover object-left -z-10" />
        <div className="absolute inset-0 -z-10 bg-gradient-to-t from-[#00071C] via-[#00071C]/60 to-[#00071C]/30" aria-hidden />

        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-lg bg-primary flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <div>
            <p className="text-xl font-bold leading-6">Trust Core</p>
            <p className="text-xs text-white/70">منصة أنظمة متكاملة لأي نشاط تجاري</p>
          </div>
        </div>

        <div className="relative space-y-8">
          <h2 className="text-4xl font-bold leading-[1.4]">
            كل أنظمة شغلك،
            <br />
            في مكان واحد.
          </h2>
          <ul className="space-y-4">
            {highlights.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-white/80">
                <span className="w-9 h-9 rounded-md bg-white/10 flex items-center justify-center">
                  <Icon className="w-[18px] h-[18px] text-white" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-white/60">© {new Date().getFullYear()} Trust Core</p>
      </aside>
    </div>
  );
}
