"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Loader2, Info, TrendingUp } from "lucide-react";

interface RevenueTrendPoint {
  month: string; // "YYYY-MM"
  revenue_egp: number;
}

interface RevenueTrendResponse {
  months: RevenueTrendPoint[];
  source: string;
}

const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("ar-EG", { month: "short" });
};

const egp = (value: number) =>
  `${value.toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

/**
 * RevenueTrendChart — real monthly revenue over the last N months, from
 * GET /reporting/revenue-trend (app.modules.reporting.router, which wraps
 * the exact same get_revenue_trend function the AI Bot can call). Plain
 * inline SVG bars — no charting library — so this stays a single
 * dependency-free component.
 *
 * Replaces the dashboard's previous "not wired up yet" placeholder for
 * "ترند الإيرادات السنوية" (see app/dashboard/page.tsx's DemoDataNotice
 * docstring) now that a real, non-fabricated monthly series exists.
 */
export function RevenueTrendChart({ months = 6 }: { months?: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reporting-revenue-trend", months],
    queryFn: async () =>
      (
        await apiClient.get<RevenueTrendResponse>("/reporting/revenue-trend", {
          params: { months },
        })
      ).data,
  });

  if (isLoading) {
    return (
      <div className="glass-card rounded-xl p-card-padding shadow-card flex items-center justify-center min-h-[220px]">
        <Loader2 className="w-5 h-5 animate-spin text-outline" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="glass-card rounded-xl p-card-padding shadow-card flex flex-col items-center justify-center text-center min-h-[220px] gap-2">
        <Info className="w-5 h-5 text-outline" />
        <p className="text-body-sm text-on-surface-variant">تعذر تحميل ترند الإيرادات.</p>
      </div>
    );
  }

  const points = data.months;
  const max = Math.max(1, ...points.map((p) => p.revenue_egp));
  const total = points.reduce((s, p) => s + p.revenue_egp, 0);

  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card min-h-[220px]" dir="rtl">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h4 className="font-headline-sm text-headline-sm">ترند الإيرادات</h4>
          <p className="text-body-sm text-outline">آخر {points.length} أشهر — إجمالي {egp(total)}</p>
        </div>
        <div className="p-2 bg-primary-container/10 rounded-lg">
          <TrendingUp className="w-4 h-4 text-primary" />
        </div>
      </div>

      <div className="flex items-end justify-between gap-2 h-32" dir="ltr">
        {points.map((p) => {
          const heightPct = Math.max(4, Math.round((p.revenue_egp / max) * 100));
          return (
            <div key={p.month} className="flex-1 flex flex-col items-center justify-end h-full gap-1 group">
              <span className="text-[10px] text-outline-variant opacity-0 group-hover:opacity-100 transition-opacity font-data-mono" dir="ltr">
                {egp(p.revenue_egp)}
              </span>
              <div
                className="w-full max-w-[28px] rounded-t bg-primary/80 group-hover:bg-primary transition-colors"
                style={{ height: `${heightPct}%` }}
                title={egp(p.revenue_egp)}
              />
              <span className="text-[10px] text-outline mt-1">{monthLabel(p.month)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
