"use client";

import { useEffect } from "react";
import { useAppStore } from "@/store/use-app-store";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import ExpirationAlertsWidget from "@/components/ExpirationAlertsWidget";
import OnboardingChecklist from "@/components/OnboardingChecklist";
import { StatusBadge, type BadgeTone } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  Users,
  FileDown,
  Plus,
  Loader2,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  ShoppingCart,
  Wallet,
  Landmark,
  ArrowDownToLine,
  ArrowUpFromLine,
  MoreVertical,
} from "lucide-react";

interface DashboardMetrics {
  total_revenue: string | number;
  total_receivables: string | number;
  total_payables: string | number;
  cash_balance: string | number;
}

interface TransactionLine {
  id: string;
  account_code: string;
  account_name: string;
  debit: string | number;
  credit: string | number;
  description: string | null;
}

interface JournalEntry {
  id: string;
  reference: string;
  description: string;
  status: "DRAFT" | "POSTED" | "VOIDED" | string;
  source_type: string | null;
  created_at: string;
  posted_at: string | null;
  lines: TransactionLine[];
}

const egp = (value: string | number) =>
  `${Number(value).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const statusLabel: Record<string, string> = {
  POSTED: "مكتمل",
  DRAFT: "قيد المراجعة",
  VOIDED: "ملغي",
};

const statusTone: Record<string, BadgeTone> = {
  POSTED: "secondary",
  DRAFT: "primary",
  VOIDED: "error",
};

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({
  label,
  value,
  trend,
  trendValue,
  icon,
  iconBg,
  iconColor,
}: {
  label: string;
  value: string;
  trend: "up" | "down" | "neutral";
  trendValue: string;
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
}) {
  return (
    <div className="glass-card p-card-padding rounded-xl shadow-card hover:shadow-overlay hover:-translate-y-0.5 transition-all duration-200">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2 ${iconBg} rounded-lg`}>{icon}</div>
        <span
          className={`flex items-center font-data-mono text-body-sm px-2 py-0.5 rounded gap-0.5 ${
            trend === "up"
              ? "text-secondary bg-secondary-container/20"
              : trend === "down"
              ? "text-error bg-error-container/20"
              : "text-outline bg-surface-container"
          }`}
        >
          {trend === "up" ? <TrendingUp className="w-3.5 h-3.5" /> : trend === "down" ? <TrendingDown className="w-3.5 h-3.5" /> : null}
          {trendValue}
        </span>
      </div>
      <p className="text-body-sm text-outline font-medium">{label}</p>
      <h3 className="font-headline-md text-headline-md mt-1" dir="ltr">{value}</h3>
      <p className="text-[10px] text-outline-variant mt-2">مقارنة بالشهر الماضي</p>
    </div>
  );
}

// ── Revenue SVG Chart ─────────────────────────────────────────────────────────
function RevenueChart() {
  const months = ["يناير", "مارس", "مايو", "يوليو", "سبتمبر", "نوفمبر"];
  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card">
      <div className="flex justify-between items-center mb-6">
        <h4 className="font-headline-sm text-headline-sm">ترند الإيرادات السنوية</h4>
        <select className="bg-surface-container-low border-none rounded text-body-sm px-3 py-1 outline-none cursor-pointer text-on-surface-variant">
          <option>آخر 12 شهر</option>
          <option>2024</option>
          <option>2023</option>
        </select>
      </div>
      <div className="relative h-64">
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 800 240" preserveAspectRatio="none">
          <defs>
            <linearGradient id="revGrad" x1="0%" x2="0%" y1="0%" y2="100%">
              <stop offset="0%" style={{ stopColor: "#00288e", stopOpacity: 0.15 }} />
              <stop offset="100%" style={{ stopColor: "#00288e", stopOpacity: 0 }} />
            </linearGradient>
          </defs>
          {/* Grid lines */}
          {[0, 60, 120, 180, 240].map((y) => (
            <line key={y} x1="0" y1={y} x2="800" y2={y} stroke="#c4c5d5" strokeWidth="0.5" />
          ))}
          {/* Area fill */}
          <path
            d="M0,200 Q100,160 200,120 T400,80 T600,140 T800,40 L800,240 L0,240 Z"
            fill="url(#revGrad)"
          />
          {/* Line */}
          <path
            d="M0,200 Q100,160 200,120 T400,80 T600,140 T800,40"
            fill="none"
            stroke="#00288e"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          {/* Data points */}
          {[
            [200, 120],
            [400, 80],
            [600, 140],
            [800, 40],
          ].map(([cx, cy]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="5" fill="#00288e" stroke="white" strokeWidth="2" />
          ))}
          {/* Y-axis labels */}
          {["500k", "400k", "300k", "200k", "100k"].map((label, i) => (
            <text key={label} x="0" y={i * 48 + 12} fill="#757684" fontSize="10" fontFamily="Inter">
              {label}
            </text>
          ))}
        </svg>
        {/* X-axis labels */}
        <div className="absolute bottom-0 w-full flex justify-between text-[10px] text-outline font-medium px-2">
          {months.map((m) => (
            <span key={m}>{m}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Expense Donut ─────────────────────────────────────────────────────────────
function ExpenseDonut() {
  const segments = [
    { label: "الرواتب", pct: 45, color: "#00288e" },
    { label: "التشغيل", pct: 25, color: "#440098" },
    { label: "أخرى", pct: 30, color: "#b8c4ff" },
  ];
  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card flex flex-col">
      <h4 className="font-headline-sm text-headline-sm mb-6">توزيع المصروفات</h4>
      <div className="relative w-40 h-40 mx-auto mb-6">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          {/* Track */}
          <circle cx="18" cy="18" r="15.915" fill="none" stroke="#e1e3e4" strokeWidth="3.5" />
          {/* Segments */}
          {(() => {
            let offset = 0;
            return segments.map((seg) => {
              const dash = (seg.pct / 100) * 100;
              const el = (
                <circle
                  key={seg.label}
                  cx="18"
                  cy="18"
                  r="15.915"
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="3.5"
                  strokeDasharray={`${dash} ${100 - dash}`}
                  strokeDashoffset={-offset}
                  strokeLinecap="round"
                />
              );
              offset += dash;
              return el;
            });
          })()}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-body-sm text-outline">الإجمالي</span>
          <span className="font-data-mono font-bold text-headline-sm">1.2M</span>
        </div>
      </div>
      <div className="space-y-3 mt-auto">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: seg.color }} />
              <span className="text-body-md">{seg.label}</span>
            </div>
            <span className="font-data-mono text-body-md font-bold">{seg.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Branch Performance ────────────────────────────────────────────────────────
function BranchPerformance() {
  const branches = [
    { name: "فرع القاهرة (الرئيسي)", value: "2.1M ج.م", pct: 85, color: "bg-primary" },
    { name: "فرع الإسكندرية", value: "1.4M ج.م", pct: 60, color: "bg-primary-container" },
    { name: "فرع الجيزة", value: "0.75M ج.م", pct: 35, color: "bg-secondary" },
  ];
  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card">
      <div className="flex justify-between items-center mb-6">
        <h4 className="font-headline-sm text-headline-sm">أداء الفروع الكبرى</h4>
        <button className="text-on-surface-variant hover:text-on-surface transition-colors">
          <MoreVertical className="w-5 h-5" />
        </button>
      </div>
      <div className="space-y-5">
        {branches.map((b) => (
          <div key={b.name}>
            <div className="flex justify-between text-body-sm mb-2">
              <span className="font-medium">{b.name}</span>
              <span className="font-data-mono">{b.value}</span>
            </div>
            <div className="w-full bg-surface-container rounded-full h-2 overflow-hidden">
              <div className={`${b.color} h-full rounded-full transition-all`} style={{ width: `${b.pct}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user } = useAppStore();
  const router = useRouter();

  useEffect(() => {
    if (!user) {
      router.push("/login");
    }
  }, [user, router]);

  const {
    data: metrics,
    isLoading: metricsLoading,
    isError: metricsError,
  } = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: async () => (await apiClient.get<DashboardMetrics>("/dashboard/metrics")).data,
    enabled: !!user,
  });

  const {
    data: entries,
    isLoading: entriesLoading,
    isError: entriesError,
  } = useQuery({
    queryKey: ["dashboard-recent-entries"],
    queryFn: async () =>
      (await apiClient.get<JournalEntry[]>("/accounting/journal-entries", { params: { limit: 6 } })).data,
    enabled: !!user,
  });

  const loading = metricsLoading || entriesLoading;
  const hasError = metricsError || entriesError;
  const entryList = entries ?? [];

  const handleExport = () => {
    if (!metrics) return;
    const rows: string[][] = [
      ["المقياس", "القيمة (ج.م)"],
      ["إجمالي الإيرادات", String(metrics.total_revenue)],
      ["إجمالي المستحقات (ذمم مدينة)", String(metrics.total_receivables)],
      ["إجمالي الالتزامات (ذمم دائنة)", String(metrics.total_payables)],
      ["رصيد النقدية", String(metrics.cash_balance)],
    ];
    const csv = "\uFEFF" + rows.map((r) => r.map((cell) => `"${(cell ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `dashboard-export-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (!user) return null;

  // Build KPI cards from API data or use demo data while loading
  const kpis = metrics
    ? [
        {
          label: "إجمالي الإيرادات",
          value: egp(metrics.total_revenue),
          trend: "up" as const,
          trendValue: "12%+",
          iconBg: "bg-primary-container/10",
          iconColor: "text-primary",
          icon: <Wallet className="w-5 h-5 text-primary" />,
        },
        {
          label: "عدد الطلبات",
          value: "1,842",
          trend: "up" as const,
          trendValue: "8%+",
          iconBg: "bg-tertiary-container/10",
          iconColor: "text-tertiary",
          icon: <ShoppingCart className="w-5 h-5 text-tertiary" />,
        },
        {
          label: "العملاء الجدد",
          value: "312",
          trend: "down" as const,
          trendValue: "2%-",
          iconBg: "bg-secondary-container/10",
          iconColor: "text-secondary",
          icon: <Users className="w-5 h-5 text-secondary" />,
        },
        {
          label: "صافي الربح",
          value: egp(metrics.cash_balance),
          trend: "up" as const,
          trendValue: "5%+",
          iconBg: "bg-error-container/10",
          iconColor: "text-error",
          icon: <Landmark className="w-5 h-5 text-error" />,
        },
      ]
    : [];

  return (
    <div className="space-y-gutter" dir="rtl">
      {/* ── Page Header ────────────────────────────────────────── */}
      <div className="flex justify-between items-center mb-2 flex-col sm:flex-row gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">لوحة تحليلات الأداء</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            مرحباً بك{user.name ? `، ${user.name}` : ""} — إليك نظرة شاملة على أداء الشركة في مصر.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleExport}
            disabled={!metrics}
            className="bg-white border border-outline-variant px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:bg-surface-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FileDown className="w-4 h-4 text-outline" />
            تصدير البيانات
          </button>
          <Link
            href="/dashboard/contacts"
            className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity"
          >
            <Plus className="w-4 h-4" />
            تقرير جديد
          </Link>
        </div>
      </div>

      <OnboardingChecklist />

      {hasError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          تعذر تحميل بيانات لوحة القيادة. تحقق من اتصال الخادم.
        </div>
      )}

      {loading ? (
        <>
          {/* Skeleton KPI cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="glass-card rounded-xl p-card-padding animate-pulse">
                <div className="w-9 h-9 rounded-lg bg-surface-container-high mb-4" />
                <div className="h-3 w-24 rounded bg-surface-container-high mb-3" />
                <div className="h-6 w-32 rounded bg-surface-container-high" />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2 text-on-surface-variant py-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-body-sm">جاري تحميل البيانات...</span>
          </div>
        </>
      ) : (
        <>
          {/* ── KPI Grid ─────────────────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
            {kpis.map((kpi) => (
              <KpiCard key={kpi.label} {...kpi} />
            ))}
          </div>

          <ExpirationAlertsWidget />

          {/* ── Charts Row ───────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
            <div className="lg:col-span-2">
              <RevenueChart />
            </div>
            <ExpenseDonut />
          </div>

          {/* ── Branch Performance ───────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter">
            <BranchPerformance />

            {/* Update highlight card */}
            <div className="relative rounded-xl overflow-hidden shadow-card group min-h-[200px]">
              <div className="absolute inset-0 z-10 bg-gradient-to-l from-primary/90 to-primary-container/70 flex flex-col justify-center p-card-padding text-white">
                <h4 className="font-headline-md text-headline-md mb-2">تحديثات النظام الجديدة</h4>
                <p className="text-body-md opacity-90 max-w-xs mb-6">
                  لقد قمنا بتحديث نظام إدارة المخازن ليتوافق مع معايير الفاتورة الإلكترونية المصرية الجديدة.
                </p>
                <Link
                  href="/dashboard/eta"
                  className="bg-white text-primary px-6 py-2 rounded-lg font-bold w-fit hover:bg-opacity-90 transition-all active:scale-95 text-body-md"
                >
                  استكشف التحديث
                </Link>
              </div>
              <div
                className="absolute inset-0 transition-transform duration-700 group-hover:scale-110"
                style={{
                  background:
                    "linear-gradient(135deg, #00288e 0%, #1e40af 40%, #440098 100%)",
                }}
              />
            </div>
          </div>

          {/* ── Recent Transactions Table ─────────────────────── */}
          <div className="glass-card rounded-xl shadow-card overflow-hidden">
            <div className="p-card-padding border-b border-outline-variant flex justify-between items-center bg-white">
              <h4 className="font-headline-sm text-headline-sm">آخر المعاملات المالية</h4>
              <Link
                href="/dashboard/accounting"
                className="text-primary text-body-sm font-bold hover:underline"
              >
                عرض الكل
              </Link>
            </div>

            {entryList.length === 0 ? (
              <EmptyState
                icon={Users}
                title="لا توجد قيود محاسبية بعد."
                description="هتظهر هنا أول ما تبدأ تسجّل فواتير أو عمليات مالية."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-right">
                  <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                    <tr>
                      <th className="px-6 py-4">المعرف</th>
                      <th className="px-6 py-4">العميل / المورد</th>
                      <th className="px-6 py-4">التاريخ</th>
                      <th className="px-6 py-4">الحالة</th>
                      <th className="px-6 py-4">المبلغ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/30 text-body-md">
                    {entryList.map((entry) => {
                      const total = entry.lines.reduce((sum, l) => sum + Number(l.debit || 0), 0);
                      return (
                        <tr
                          key={entry.id}
                          className="hover:bg-surface-container-lowest transition-colors cursor-pointer"
                        >
                          <td className="px-6 py-4 font-data-mono" dir="ltr">
                            {entry.reference}
                          </td>
                          <td className="px-6 py-4 font-medium">{entry.description}</td>
                          <td className="px-6 py-4 text-outline">
                            {new Date(entry.created_at).toLocaleDateString("ar-EG")}
                          </td>
                          <td className="px-6 py-4">
                            <StatusBadge tone={statusTone[entry.status] ?? "neutral"}>
                              {statusLabel[entry.status] ?? entry.status}
                            </StatusBadge>
                          </td>
                          <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">
                            {egp(total)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
