"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Loader2, Info, PieChart } from "lucide-react";

interface ExpenseItem {
  account_code: string;
  account_name: string;
  amount_egp: number;
}

interface ExpenseBreakdownResponse {
  total_expenses_egp: number;
  items: ExpenseItem[];
  source: string;
}

const egp = (value: number) =>
  `${value.toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const barColors = [
  "bg-primary",
  "bg-secondary",
  "bg-tertiary",
  "bg-error",
  "bg-outline",
];

/**
 * ExpenseBreakdownChart — real expense totals for the current calendar
 * month, grouped by chart-of-accounts expense account, from
 * GET /reporting/expense-breakdown. Horizontal bar list instead of a pie
 * — easier to read account names against, and no charting library needed.
 *
 * Replaces the dashboard's previous "not wired up yet" placeholder for
 * "توزيع المصروفات".
 */
export function ExpenseBreakdownChart() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reporting-expense-breakdown"],
    queryFn: async () =>
      (await apiClient.get<ExpenseBreakdownResponse>("/reporting/expense-breakdown")).data,
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
        <p className="text-body-sm text-on-surface-variant">تعذر تحميل توزيع المصروفات.</p>
      </div>
    );
  }

  const items = data.items;

  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card min-h-[220px]" dir="rtl">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h4 className="font-headline-sm text-headline-sm">توزيع المصروفات</h4>
          <p className="text-body-sm text-outline">هذا الشهر — إجمالي {egp(data.total_expenses_egp)}</p>
        </div>
        <div className="p-2 bg-error-container/10 rounded-lg">
          <PieChart className="w-4 h-4 text-error" />
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant text-center py-8">
          لا توجد مصروفات مُرحّلة هذا الشهر بعد.
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((item, i) => {
            const pct = data.total_expenses_egp > 0 ? Math.round((item.amount_egp / data.total_expenses_egp) * 100) : 0;
            return (
              <div key={item.account_code}>
                <div className="flex justify-between text-body-sm mb-1">
                  <span className="font-medium">{item.account_name}</span>
                  <span className="font-data-mono text-outline" dir="ltr">{egp(item.amount_egp)}</span>
                </div>
                <div className="w-full h-2 rounded-full bg-surface-container-high overflow-hidden">
                  <div
                    className={`h-full rounded-full ${barColors[i % barColors.length]}`}
                    style={{ width: `${Math.max(2, pct)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
