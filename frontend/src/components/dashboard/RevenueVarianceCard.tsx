"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Loader2, Info, TrendingUp, TrendingDown } from "lucide-react";

interface Mover {
  customer_name: string;
  this_month_egp: number;
  last_month_egp: number;
  delta_egp: number;
}

interface RevenueVarianceResponse {
  this_month_revenue_egp: number;
  last_month_revenue_egp: number;
  delta_egp: number;
  delta_pct: number | null;
  breakdown: {
    new_customers_this_month_revenue_egp: number;
    returning_customers_this_month_revenue_egp: number;
    returning_customers_last_month_revenue_egp: number;
  };
  top_movers: Mover[];
  source: string;
}

const egp = (value: number) =>
  `${value.toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

/**
 * RevenueVarianceCard — surfaces Copilot Level 2's deterministic
 * decomposition (GET /reporting/revenue-variance, same function as
 * REPORT_REGISTRY's get_revenue_variance_analysis) as a dashboard widget
 * instead of requiring a WhatsApp/chat question to see it. Same numbers,
 * same guarantee: a real GROUP BY, never an LLM guess at "why".
 */
export function RevenueVarianceCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reporting-revenue-variance"],
    queryFn: async () =>
      (await apiClient.get<RevenueVarianceResponse>("/reporting/revenue-variance")).data,
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
        <p className="text-body-sm text-on-surface-variant">تعذر تحميل تحليل الإيرادات.</p>
      </div>
    );
  }

  const up = data.delta_egp >= 0;

  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card" dir="rtl">
      <h4 className="font-headline-sm text-headline-sm mb-1">ليه الإيرادات اتغيرت؟</h4>
      <p className="text-body-sm text-outline mb-4">هذا الشهر مقابل الشهر الماضي</p>

      <div className="flex items-center gap-3 mb-4">
        <div className={`p-2 rounded-lg ${up ? "bg-secondary-container/20" : "bg-error-container/20"}`}>
          {up ? <TrendingUp className="w-5 h-5 text-secondary" /> : <TrendingDown className="w-5 h-5 text-error" />}
        </div>
        <div>
          <p className="font-data-mono text-headline-sm" dir="ltr">
            {up ? "+" : ""}
            {egp(data.delta_egp)}
          </p>
          <p className="text-body-sm text-outline">
            {data.delta_pct === null ? "لا توجد بيانات مقارنة" : `${Math.abs(data.delta_pct)}%${up ? "+" : "-"}`}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="bg-surface-container rounded-lg p-3">
          <p className="text-[10px] text-outline">من عملاء جدد</p>
          <p className="font-data-mono text-body-md" dir="ltr">
            {egp(data.breakdown.new_customers_this_month_revenue_egp)}
          </p>
        </div>
        <div className="bg-surface-container rounded-lg p-3">
          <p className="text-[10px] text-outline">من عملاء متكررين</p>
          <p className="font-data-mono text-body-md" dir="ltr">
            {egp(data.breakdown.returning_customers_this_month_revenue_egp)}
          </p>
        </div>
      </div>

      {data.top_movers.length > 0 && (
        <div>
          <p className="text-body-sm font-medium mb-2">أكبر التغييرات</p>
          <div className="space-y-1.5">
            {data.top_movers.map((m) => (
              <div key={m.customer_name} className="flex justify-between text-body-sm">
                <span className="text-on-surface-variant">{m.customer_name}</span>
                <span
                  className={`font-data-mono ${m.delta_egp >= 0 ? "text-secondary" : "text-error"}`}
                  dir="ltr"
                >
                  {m.delta_egp >= 0 ? "+" : ""}
                  {egp(m.delta_egp)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
