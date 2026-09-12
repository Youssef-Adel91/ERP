"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Loader2, Info, Trophy } from "lucide-react";

interface CustomerRow {
  customer_name: string;
  total_billed_egp: number;
  invoice_count: number;
}

interface TopCustomersResponse {
  customers: CustomerRow[];
  source: string;
}

const egp = (value: number) =>
  `${value.toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

/** TopCustomersCard — GET /reporting/top-customers, same function the AI Bot uses. */
export function TopCustomersCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reporting-top-customers"],
    queryFn: async () =>
      (await apiClient.get<TopCustomersResponse>("/reporting/top-customers", { params: { limit: 5 } })).data,
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
        <p className="text-body-sm text-on-surface-variant">تعذر تحميل أكبر العملاء.</p>
      </div>
    );
  }

  const max = Math.max(1, ...data.customers.map((c) => c.total_billed_egp));

  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card" dir="rtl">
      <div className="flex items-center gap-2 mb-4">
        <div className="p-2 bg-tertiary-container/10 rounded-lg">
          <Trophy className="w-4 h-4 text-tertiary" />
        </div>
        <h4 className="font-headline-sm text-headline-sm">أكبر العملاء</h4>
      </div>

      {data.customers.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant text-center py-8">لا توجد فواتير مُرحّلة بعد.</p>
      ) : (
        <div className="space-y-3">
          {data.customers.map((c, i) => (
            <div key={c.customer_name}>
              <div className="flex justify-between text-body-sm mb-1">
                <span className="font-medium">
                  {i + 1}. {c.customer_name}
                  <span className="text-outline-variant text-[10px] mr-1">({c.invoice_count} فاتورة)</span>
                </span>
                <span className="font-data-mono text-outline" dir="ltr">{egp(c.total_billed_egp)}</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-surface-container-high overflow-hidden">
                <div
                  className="h-full rounded-full bg-tertiary"
                  style={{ width: `${Math.max(2, Math.round((c.total_billed_egp / max) * 100))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
