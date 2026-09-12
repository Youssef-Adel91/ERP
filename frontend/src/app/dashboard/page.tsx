"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/store/use-app-store";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import ExpirationAlertsWidget from "@/components/ExpirationAlertsWidget";
import OnboardingChecklist from "@/components/OnboardingChecklist";
import { StatusBadge, type BadgeTone } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { RevenueTrendChart } from "@/components/dashboard/RevenueTrendChart";
import { ExpenseBreakdownChart } from "@/components/dashboard/ExpenseBreakdownChart";
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
  Info,
  Sparkles,
} from "lucide-react";

interface DashboardMetrics {
  total_revenue: string | number;
  total_receivables: string | number;
  total_payables: string | number;
  cash_balance: string | number;
  order_count: number;
  order_count_trend_pct: number | null;
  new_customers_count: number;
  new_customers_trend_pct: number | null;
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

// ── Demo Data Notice ────────────────────────────────────────────────────────
// Replaces three previously-fake charts (revenue trend, expense breakdown,
// branch performance) that rendered invented numbers and fictional branch
// names not connected to any real tenant data. Per
// docs/Nexus_ERP_Audit_Report.md §15's own proposed remedy, a chart backed
// by real aggregation logic (branch revenue, expense-category breakdown)
// isn't wired up here yet — that requires business logic (branch/cost-center
// data model) not yet confirmed to exist cleanly for this tenant. Showing an
// honest placeholder is safer than either shipping fabricated numbers or
// guessing at unverified aggregation logic.
function DemoDataNotice({ title }: { title: string }) {
  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card flex flex-col items-center justify-center text-center min-h-[200px] gap-3">
      <div className="p-2 bg-surface-container rounded-lg">
        <Info className="w-5 h-5 text-outline" />
      </div>
      <h4 className="font-headline-sm text-headline-sm">{title}</h4>
      <p className="text-body-sm text-on-surface-variant max-w-xs">
        هذا الرسم البياني غير متاح بعد — يحتاج ربطًا ببيانات حقيقية لم تُفعَّل في هذا الإصدار.
      </p>
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

  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (!metrics || exporting) return;
    setExporting(true);
    try {
      const response = await apiClient.get("/dashboard/export.xlsx", { responseType: "blob" });
      const blob = new Blob([response.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `dashboard-export-${new Date().toISOString().slice(0, 10)}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  if (!user) return null;

  // Build KPI cards from real API data. Two of the four (order count, new
  // customers) now carry real month-over-month trend badges computed by the
  // backend; the revenue and cash-balance cards have no trend baseline
  // computed server-side yet, so their badges stay neutral rather than
  // showing an invented percentage.
  const formatTrend = (pct: number | null): { trend: "up" | "down" | "neutral"; trendValue: string } => {
    if (pct === null || pct === undefined) return { trend: "neutral", trendValue: "لا توجد بيانات مقارنة" };
    if (pct === 0) return { trend: "neutral", trendValue: "0%" };
    return { trend: pct > 0 ? "up" : "down", trendValue: `${Math.abs(pct)}%${pct > 0 ? "+" : "-"}` };
  };

  const kpis = metrics
    ? [
        {
          label: "إجمالي الإيرادات",
          value: egp(metrics.total_revenue),
          trend: "neutral" as const,
          trendValue: "لا توجد بيانات مقارنة",
          iconBg: "bg-primary-container/10",
          iconColor: "text-primary",
          icon: <Wallet className="w-5 h-5 text-primary" />,
        },
        {
          label: "عدد الطلبات",
          value: metrics.order_count.toLocaleString("ar-EG"),
          ...formatTrend(metrics.order_count_trend_pct),
          iconBg: "bg-tertiary-container/10",
          iconColor: "text-tertiary",
          icon: <ShoppingCart className="w-5 h-5 text-tertiary" />,
        },
        {
          label: "العملاء الجدد",
          value: metrics.new_customers_count.toLocaleString("ar-EG"),
          ...formatTrend(metrics.new_customers_trend_pct),
          iconBg: "bg-secondary-container/10",
          iconColor: "text-secondary",
          icon: <Users className="w-5 h-5 text-secondary" />,
        },
        {
          label: "رصيد النقدية",
          value: egp(metrics.cash_balance),
          trend: "neutral" as const,
          trendValue: "لا توجد بيانات مقارنة",
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
            disabled={!metrics || exporting}
            className="bg-white border border-outline-variant px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:bg-surface-container transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {exporting ? <Loader2 className="w-4 h-4 text-outline animate-spin" /> : <FileDown className="w-4 h-4 text-outline" />}
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

          {/* ── AI Insights Teaser ───────────────────────────── */}
          <Link
            href="/dashboard/insights"
            className="flex items-center justify-between glass-card rounded-xl p-card-padding shadow-card hover:shadow-overlay hover:-translate-y-0.5 transition-all group"
          >
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary-container/10 rounded-lg">
                <Sparkles className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h4 className="font-headline-sm text-headline-sm">رؤى الذكاء الاصطناعي</h4>
                <p className="text-body-sm text-on-surface-variant">
                  اسأل المساعد الذكي عن أرقامك، وشوف تحليل الإيرادات وأكبر العملاء والفواتير المتأخرة في مكان واحد.
                </p>
              </div>
            </div>
            <span className="text-primary text-body-sm font-bold group-hover:underline shrink-0">
              افتح اللوحة
            </span>
          </Link>

          {/* ── Charts Row ───────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
            <div className="lg:col-span-2">
              <RevenueTrendChart months={6} />
            </div>
            <ExpenseBreakdownChart />
          </div>

          {/* ── Branch Performance ───────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter">
            <DemoDataNotice title="أداء الفروع الكبرى" />

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
