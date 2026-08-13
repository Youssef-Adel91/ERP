"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  Loader2,
  AlertCircle,
  BedDouble,
  Car,
  Plane,
  UsersRound,
  MessageCircle,
  Puzzle,
  PlayCircle,
  CheckCircle2,
  LayoutGrid,
  ArrowLeft,
  Sparkles,
  Lock,
} from "lucide-react";

// ── Types (mirrors backend app/modules/system/api_plugins.py) ───────────────

interface PluginEntry {
  key: string;
  name_ar: string;
  description_ar: string;
  is_active: boolean;
  is_demo: boolean;
  video_url: string | null;
  package_key: string | null;
  demo_operations_used: number;
  demo_operation_limit: number;
}

const pluginIcon: Record<string, typeof Puzzle> = {
  hospitality: BedDouble,
  rental: Car,
  travel: Plane,
  recruitment: UsersRound,
  whatsapp: MessageCircle,
};

// Rotating accent per card — keeps the grid visually varied while staying
// inside the approved Stitch/MD3 token palette (primary/secondary/tertiary).
const ACCENTS = [
  { grad: "from-primary to-tertiary", glow: "rgba(0,40,142,0.45)", ring: "ring-primary/40", text: "text-primary" },
  { grad: "from-secondary to-primary", glow: "rgba(0,106,97,0.45)", ring: "ring-secondary/40", text: "text-secondary" },
  { grad: "from-tertiary to-secondary", glow: "rgba(68,0,152,0.45)", ring: "ring-tertiary/40", text: "text-tertiary" },
];
const accentFor = (i: number) => ACCENTS[i % ACCENTS.length];

// Core system — always included with every account, never gated.
const CORE_SYSTEM = {
  name_ar: "النظام الأساسي (المحاسبة، المبيعات، المخزون، المشتريات، الموارد البشرية)",
  description_ar: "متضمن مجانًا مع كل حساب، مفعّل بالفعل ولا يحتاج أي اختيار.",
};

export default function OnboardingSystemsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [errorMsg, setErrorMsg] = useState("");
  const [videoPlugin, setVideoPlugin] = useState<string | null>(null);

  const { data: plugins, isLoading, isError } = useQuery({
    queryKey: ["onboarding-plugins"],
    queryFn: async () => {
      const res = await apiClient.get<PluginEntry[]>("/plugins");
      return res.data;
    },
  });

  const demoMutation = useMutation({
    mutationFn: async (key: string) => {
      await apiClient.post(`/plugins/${key}/demo`);
    },
    onSuccess: () => {
      setErrorMsg("");
      queryClient.invalidateQueries({ queryKey: ["onboarding-plugins"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setErrorMsg(pickDetail(err, "تعذر تفعيل الديمو، حاول مرة أخرى."));
    },
  });

  const activateMutation = useMutation({
    mutationFn: async (key: string) => {
      await apiClient.put(`/plugins/${key}`, { is_active: true });
    },
    onSuccess: () => {
      setErrorMsg("");
      queryClient.invalidateQueries({ queryKey: ["onboarding-plugins"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setErrorMsg(pickDetail(err, "تعذر تفعيل النظام بالكامل، حاول مرة أخرى."));
    },
  });

  // Removing the "skip" option means the continue action must be earned:
  // the user has to have started a demo or fully activated at least one
  // vertical system before the dashboard CTA unlocks.
  const anyTried = plugins?.some((p) => p.is_demo || p.is_active) ?? false;

  return (
    <div
      className="min-h-screen bg-surface p-gutter"
      style={{
        backgroundImage: "radial-gradient(#e5e7eb 0.5px, transparent 0.5px)",
        backgroundSize: "24px 24px",
      }}
    >
      <main className="w-full max-w-5xl mx-auto py-10 animate-in fade-in duration-700 slide-in-from-bottom-4">
        {/* Logo & Header */}
        <div className="text-center mb-8">
          <div className="flex justify-center items-center gap-3 mb-4">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center shadow-overlay">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-7 h-7 fill-white">
                <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z" />
              </svg>
            </div>
            <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">Nexus ERP</h1>
          </div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface mb-1">
            أهلاً بيك! انهي أنظمة محتاجها؟
          </h2>
          <p className="font-body-md text-body-md text-on-surface-variant max-w-lg mx-auto">
            النظام الأساسي متاح ليك مجانًا فورًا. اختار نظام قطاعي عشان تفتح كل مميزاته، أو جرّب
            الديمو المجاني الأول قبل ما تقرر — لازم تجرّب أو تفعّل نظام واحد على الأقل عشان تكمل.
          </p>
        </div>

        {/* Core system — always included */}
        <div className="glass-card rounded-xl p-card-padding mb-gutter border border-primary flex items-start gap-4">
          <div className="w-11 h-11 rounded-lg flex items-center justify-center shrink-0 bg-primary-container/10 text-primary">
            <LayoutGrid className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-headline-sm text-headline-sm text-on-surface">{CORE_SYSTEM.name_ar}</h3>
              <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-success-bg text-success">
                مفعّل بالفعل
              </span>
            </div>
            <p className="text-body-sm text-on-surface-variant mt-1">{CORE_SYSTEM.description_ar}</p>
          </div>
        </div>

        {/* Vertical plugins */}
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-body-sm text-error py-6">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الأنظمة المتاحة.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-gutter mb-gutter">
            {plugins?.map((plugin, i) => {
              const Icon = pluginIcon[plugin.key] ?? Puzzle;
              const accent = accentFor(i);
              const isDemoPending = demoMutation.isPending && demoMutation.variables === plugin.key;
              const isActivatePending = activateMutation.isPending && activateMutation.variables === plugin.key;
              const demoUsedUp =
                plugin.is_demo && !plugin.is_active && plugin.demo_operations_used >= plugin.demo_operation_limit;

              return (
                <div
                  key={plugin.key}
                  className={`group relative overflow-hidden rounded-xl glass-card border transition-all duration-300 hover:-translate-y-1 ${
                    plugin.is_active ? "border-success" : "border-outline-variant/40 hover:border-transparent"
                  }`}
                  style={{
                    boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = `0 0 0 1px ${accent.glow}, 0 12px 40px -8px ${accent.glow}`;
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.08)";
                  }}
                >
                  {/* Image banner */}
                  <div className={`relative h-28 bg-gradient-to-br ${accent.grad} flex items-center justify-center overflow-hidden`}>
                    <div
                      className="absolute inset-0 opacity-20 transition-transform duration-500 group-hover:scale-110"
                      style={{
                        backgroundImage:
                          "radial-gradient(circle at 20% 20%, white 0, transparent 35%), radial-gradient(circle at 80% 60%, white 0, transparent 30%)",
                      }}
                    />
                    <Icon className="w-12 h-12 text-white drop-shadow-lg relative z-10 transition-transform duration-300 group-hover:scale-110" />
                    {plugin.is_active && (
                      <span className="absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-white/90 text-success">
                        <CheckCircle2 className="w-3 h-3" /> مفعّل بالكامل
                      </span>
                    )}
                    {plugin.package_key && (
                      <span className="absolute top-2 right-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-black/25 text-white backdrop-blur-sm">
                        <Sparkles className="w-3 h-3" /> جزء من باقة
                      </span>
                    )}
                  </div>

                  <div className="p-card-padding space-y-3">
                    <div>
                      <h3 className="font-headline-sm text-headline-sm text-on-surface">{plugin.name_ar}</h3>
                      <p className="text-body-sm text-on-surface-variant mt-0.5">{plugin.description_ar}</p>
                    </div>

                    {/* Demo usage meter */}
                    {plugin.is_demo && !plugin.is_active && (
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-[11px] font-semibold text-on-surface-variant">
                          <span>استخدام الديمو</span>
                          <span dir="ltr">
                            {Math.min(plugin.demo_operations_used, plugin.demo_operation_limit)}/{plugin.demo_operation_limit}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-surface-container overflow-hidden">
                          <div
                            className={`h-full rounded-full ${demoUsedUp ? "bg-error" : accent.text.replace("text-", "bg-")}`}
                            style={{
                              width: `${Math.min(100, (plugin.demo_operations_used / plugin.demo_operation_limit) * 100)}%`,
                            }}
                          />
                        </div>
                        {demoUsedUp && (
                          <p className="text-[11px] text-error font-semibold">
                            خلصت حدود الديمو — فعّل النظام بالكامل عشان تكمل.
                          </p>
                        )}
                      </div>
                    )}

                    <div className="flex items-center gap-2 flex-wrap pt-1">
                      {plugin.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-body-sm font-bold bg-success-bg text-success">
                          <CheckCircle2 className="w-4 h-4" /> جاهز للاستخدام الكامل
                        </span>
                      ) : (
                        <>
                          {!plugin.is_demo && (
                            <button
                              onClick={() => demoMutation.mutate(plugin.key)}
                              disabled={isDemoPending}
                              className="h-9 px-4 rounded-lg border border-outline-variant text-on-surface font-bold text-body-sm hover:bg-surface-container transition-colors disabled:opacity-70 inline-flex items-center gap-1.5"
                            >
                              {isDemoPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                              جرّب الديمو
                            </button>
                          )}
                          <button
                            onClick={() => activateMutation.mutate(plugin.key)}
                            disabled={isActivatePending}
                            className={`h-9 px-4 rounded-lg bg-gradient-to-br ${accent.grad} text-white font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70 inline-flex items-center gap-1.5`}
                          >
                            {isActivatePending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
                            استكمال النظام بالكامل
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => setVideoPlugin(plugin.key)}
                        className="h-9 px-3 rounded-lg text-on-surface-variant font-semibold text-body-sm hover:bg-surface-container transition-colors inline-flex items-center gap-1.5"
                      >
                        <PlayCircle className="w-4 h-4" /> شاهد الشرح
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error mb-gutter">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}

        {/* Footer action — no skip; must try a demo or fully activate a
            system first, per explicit product decision. */}
        <div className="flex flex-col items-end gap-2 pt-2">
          {!anyTried && (
            <p className="text-body-sm text-on-surface-variant">
              اختار نظام وجرّب الديمو أو فعّله بالكامل عشان تقدر تكمل للوحة التحكم.
            </p>
          )}
          <button
            onClick={() => anyTried && router.push("/dashboard")}
            disabled={!anyTried}
            aria-disabled={!anyTried}
            className={`h-11 px-6 rounded-lg font-bold text-body-md inline-flex items-center gap-2 transition-opacity ${
              anyTried
                ? "bg-primary text-on-primary hover:opacity-90"
                : "bg-surface-container text-on-surface-variant cursor-not-allowed opacity-70"
            }`}
          >
            متابعة إلى لوحة التحكم
            <ArrowLeft className="w-4 h-4" />
          </button>
        </div>
      </main>

      {/* Explainer video placeholder modal — no video assets exist yet */}
      {videoPlugin && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-gutter"
          onClick={() => setVideoPlugin(null)}
        >
          <div
            className="glass-card rounded-xl p-8 max-w-md w-full text-center space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <PlayCircle className="w-10 h-10 text-primary mx-auto" />
            <h3 className="font-headline-sm text-headline-sm text-on-surface">الفيديو التعريفي قريبًا</h3>
            <p className="text-body-sm text-on-surface-variant">
              بنجهز فيديو شرح قصير لكل نظام. لحد ما يكون جاهز، جرّب الديمو المجاني عشان تاخد فكرة بنفسك.
            </p>
            <button
              onClick={() => setVideoPlugin(null)}
              className="h-10 px-5 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity"
            >
              تمام
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
