"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Loader2, Info, AlertTriangle } from "lucide-react";

interface OverdueInvoice {
  invoice_number: string;
  customer_name: string;
  due_date: string;
  days_overdue: number;
  grand_total_egp: number;
  currency: string;
}

interface OverdueInvoicesResponse {
  count: number;
  total_overdue_egp: number;
  invoices: OverdueInvoice[];
  source: string;
}

const egp = (value: number) =>
  `${value.toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

/**
 * OverdueInvoicesCard — GET /reporting/overdue-invoices, the exact same
 * POSTED + due_date < today filter used by both the AI Bot
 * (get_overdue_invoices) and the WhatsApp/email reminder engine
 * (process_overdue_reminders) — so this list can never disagree with
 * what's actually being chased.
 */
export function OverdueInvoicesCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["reporting-overdue-invoices"],
    queryFn: async () =>
      (await apiClient.get<OverdueInvoicesResponse>("/reporting/overdue-invoices", { params: { limit: 8 } })).data,
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
        <p className="text-body-sm text-on-surface-variant">تعذر تحميل الفواتير المتأخرة.</p>
      </div>
    );
  }

  return (
    <div className="glass-card rounded-xl p-card-padding shadow-card" dir="rtl">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-error-container/10 rounded-lg">
            <AlertTriangle className="w-4 h-4 text-error" />
          </div>
          <h4 className="font-headline-sm text-headline-sm">فواتير متأخرة السداد</h4>
        </div>
        {data.count > 0 && (
          <span className="text-body-sm font-data-mono text-error" dir="ltr">
            {egp(data.total_overdue_egp)}
          </span>
        )}
      </div>

      {data.invoices.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant text-center py-8">لا توجد فواتير متأخرة حاليًا 🎉</p>
      ) : (
        <div className="space-y-2">
          {data.invoices.map((inv) => (
            <div
              key={inv.invoice_number}
              className="flex items-center justify-between py-2 border-b border-outline-variant/30 last:border-0"
            >
              <div>
                <p className="text-body-sm font-medium">{inv.customer_name}</p>
                <p className="text-[10px] text-outline-variant font-data-mono" dir="ltr">
                  {inv.invoice_number}
                </p>
              </div>
              <div className="text-left" dir="ltr">
                <p className="text-body-sm font-data-mono font-bold">{egp(inv.grand_total_egp)}</p>
                <p className="text-[10px] text-error">متأخرة {inv.days_overdue} يوم</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
