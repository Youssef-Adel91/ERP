import { ShieldCheck, BarChart3, Boxes, Sparkles } from "lucide-react";

const highlights = [
  { icon: BarChart3, text: "تقارير مبيعات ومخزون لحظية" },
  { icon: Boxes, text: "إدارة الفروع والموردين في مكان واحد" },
  { icon: Sparkles, text: "Trust AI يلخص لك يومك ويقترح قراراتك" },
];

export default function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-surface grid lg:grid-cols-2">
      <div className="flex flex-col items-center justify-center p-6 lg:p-12">{children}</div>

      <aside className="hidden lg:flex flex-col justify-between bg-sidebar text-on-sidebar p-12 relative overflow-hidden">
        <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-primary/30 blur-3xl" />
        <div className="absolute -bottom-32 -right-16 w-96 h-96 rounded-full bg-tertiary/20 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-lg bg-primary flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <div>
            <p className="text-xl font-bold leading-6">Trust Core</p>
            <p className="text-xs text-sidebar-text">المرجع الرقمي للتاجر المصري</p>
          </div>
        </div>

        <div className="relative space-y-8">
          <h2 className="text-4xl font-bold leading-[1.4]">
            كل أعمال تجارتك،
            <br />
            في نظام واحد تثق فيه.
          </h2>
          <ul className="space-y-4">
            {highlights.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sidebar-text">
                <span className="w-9 h-9 rounded-md bg-sidebar-hover flex items-center justify-center">
                  <Icon className="w-[18px] h-[18px] text-on-sidebar" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-sidebar-text">© {new Date().getFullYear()} Trust Core</p>
      </aside>
    </div>
  );
}
