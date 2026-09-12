"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  Plane,
  Loader2,
  AlertCircle,
  Users2,
  TrendingUp,
  Wallet,
  ArrowUpRight,
  Package,
  Stamp,
  FileDown,
} from "lucide-react";
import ExpirationAlertsWidget from "@/components/ExpirationAlertsWidget";

interface CaseType {
  id: string;
  code: string;
  plugin_key: string;
}

interface TravelBooking {
  id: string;
  title: string | null;
  current_stage: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  data: Record<string, any>;
}

interface TravelFinancials {
  case_id: string;
  currency: string;
  total_buy_price: string;
  total_sell_price: string;
  total_margin: string;
  margin_pct: string;
  commission_amount: string;
  passenger_count: number;
}

const stageLabel: Record<string, string> = {
  inquiry: "استفسار",
  quotation: "تم إرسال العرض",
  confirmed: "تم التأكيد",
  ticketed: "تم إصدار التذاكر",
  completed: "اكتملت الرحلة",
  closed: "مغلق",
  cancelled: "ملغي",
};

const stageTone: Record<string, string> = {
  inquiry: "bg-surface-container text-on-surface-variant",
  quotation: "bg-primary-container/10 text-primary",
  confirmed: "bg-tertiary-container/20 text-tertiary",
  ticketed: "bg-secondary-container/30 text-secondary",
  completed: "bg-secondary-container/30 text-secondary",
  closed: "bg-surface-container text-outline",
  cancelled: "bg-error-container/40 text-error",
};

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

export default function TravelPage() {
  const [showClosed, setShowClosed] = useState(false);

  const { data: caseTypes } = useQuery({
    queryKey: ["case-types", "travel"],
    queryFn: async () => {
      const res = await apiClient.get<CaseType[]>("/case-types", { params: { plugin_key: "travel" } });
      return res.data;
    },
  });
  const caseType = caseTypes?.find((c) => c.code === "travel_booking");

  const { data: bookings, isLoading, isError } = useQuery({
    queryKey: ["travel-bookings", caseType?.id],
    enabled: !!caseType,
    queryFn: async () => {
      const res = await apiClient.get<TravelBooking[]>("/cases", { params: { case_type_id: caseType!.id } });
      return res.data;
    },
  });

  const visible = (bookings ?? [])
    .filter((b) => showClosed || !["closed", "cancelled"].includes(b.current_stage))
    .sort((a, b) => (a.start_date ?? "9999").localeCompare(b.start_date ?? "9999"));

  // Financials are per-booking (no bulk endpoint), so fetch them individually —
  // acceptable at the vertical's typical scale (a handful of active bookings
  // at a time, not thousands).
  const financialsQueries = useQuery({
    queryKey: ["travel-financials-bulk", visible.map((b) => b.id).join(",")],
    enabled: visible.length > 0,
    queryFn: async () => {
      const results = await Promise.all(
        visible.map(async (b) => {
          try {
            const res = await apiClient.get<TravelFinancials>(`/travel/bookings/${b.id}/financials`);
            return [b.id, res.data] as const;
          } catch {
            return [b.id, null] as const;
          }
        })
      );
      return new Map(results);
    },
  });

  const totalMargin = Array.from(financialsQueries.data?.values() ?? [])
    .filter((f): f is TravelFinancials => !!f)
    .reduce((sum, f) => sum + Number(f.total_margin), 0);

  const upcoming = visible.filter((b) => b.start_date && b.start_date >= new Date().toISOString().slice(0, 10)).slice(0, 5);

  // PDF download — was previously a plain <a href target="_blank"> straight
  // to the API URL, which never carried the Authorization bearer header
  // (this app authenticates via a bearer token in localStorage, not
  // cookies — see src/lib/api-client.ts) and so always 401'd when clicked.
  // Fixed to the same blob-download pattern already used for invoice PDFs
  // in app/dashboard/sales/page.tsx.
  const [pdfDownloadingId, setPdfDownloadingId] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState("");
  const pdfMutation = useMutation({
    mutationFn: async (booking: TravelBooking) => {
      const res = await apiClient.get(`/travel/bookings/${booking.id}/pdf`, { responseType: "blob" });
      return { booking, blob: res.data as Blob };
    },
    onMutate: (booking) => { setPdfError(""); setPdfDownloadingId(booking.id); },
    onSuccess: ({ booking, blob }) => {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `booking_${booking.id.slice(0, 8)}_confirmation.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
    onError: (err: AxiosError<{ detail?: string }>) => setPdfError(pickDetail(err, "تعذر تحميل تأكيد الحجز.")),
    onSettled: () => setPdfDownloadingId(null),
  });

  if (!caseType) {
    return (
      <div className="space-y-gutter">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">السياحة والسفر</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">حجوزات السفر والهامش الربحي.</p>
        </div>
        <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
          <Plane className="w-8 h-8 text-outline-variant" />
          <p className="text-body-md">موديول السياحة والسفر غير مفعّل بعد. فعّله من صفحة الحالات أولاً.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">السياحة والسفر</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">الرحلات القادمة والهامش الربحي لكل حجز.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link
            href="/dashboard/travel/packages"
            className="flex items-center gap-2 h-10 px-4 rounded-lg border border-outline-variant text-on-surface font-bold text-body-sm hover:bg-surface-container transition-colors w-fit"
          >
            <Package className="w-4 h-4" /> باقات السياحة
          </Link>
          <Link
            href="/dashboard/travel/visas"
            className="flex items-center gap-2 h-10 px-4 rounded-lg border border-outline-variant text-on-surface font-bold text-body-sm hover:bg-surface-container transition-colors w-fit"
          >
            <Stamp className="w-4 h-4" /> متابعة التأشيرات
          </Link>
          <Link
            href="/dashboard/travel/new"
            className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity w-fit"
          >
            حجز جديد <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-gutter">
        <div className="glass-card rounded-xl p-card-padding">
          <div className="flex items-center gap-2 text-on-surface-variant text-body-sm mb-2"><Plane className="w-4 h-4" /> حجوزات نشطة</div>
          <p className="font-headline-md text-headline-md text-on-surface font-data-mono" dir="ltr">{visible.length}</p>
        </div>
        <div className="glass-card rounded-xl p-card-padding">
          <div className="flex items-center gap-2 text-on-surface-variant text-body-sm mb-2"><Users2 className="w-4 h-4" /> رحلات خلال 5 أيام قادمة</div>
          <p className="font-headline-md text-headline-md text-on-surface font-data-mono" dir="ltr">{upcoming.length}</p>
        </div>
        <div className="glass-card rounded-xl p-card-padding">
          <div className="flex items-center gap-2 text-on-surface-variant text-body-sm mb-2"><TrendingUp className="w-4 h-4" /> إجمالي الهامش (النشط)</div>
          <p className="font-headline-md text-headline-md text-secondary font-data-mono" dir="ltr">
            {financialsQueries.isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : egp(totalMargin)}
          </p>
        </div>
      </div>

      <ExpirationAlertsWidget />

      {pdfError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {pdfError}
        </div>
      )}

      <label className="flex items-center gap-2 text-body-sm text-on-surface-variant w-fit">
        <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
        إظهار المغلقة والملغاة
      </label>

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error"><AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الحجوزات.</div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <Plane className="w-7 h-7 text-outline-variant" />
            <p className="text-body-sm">لا توجد حجوزات نشطة.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">العميل</th>
                  <th className="px-6 py-4">الوجهة</th>
                  <th className="px-6 py-4">تاريخ السفر</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4 flex items-center gap-1"><Wallet className="w-3.5 h-3.5" /> الهامش</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {visible.map((b) => {
                  const fin = financialsQueries.data?.get(b.id);
                  return (
                    <tr key={b.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4 font-medium">{b.data?.customer_name ?? "—"}</td>
                      <td className="px-6 py-4 text-on-surface-variant">{b.data?.destination ?? "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{b.start_date ?? "—"}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[11px] font-bold ${stageTone[b.current_stage] ?? ""}`}>
                          {stageLabel[b.current_stage] ?? b.current_stage}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">
                        {fin ? egp(fin.total_margin) : "—"}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <Link href={`/dashboard/cases/${b.id}`} className="flex items-center gap-1.5 text-primary font-semibold text-body-sm hover:underline">
                            التفاصيل <ArrowUpRight className="w-3.5 h-3.5" />
                          </Link>
                          <button
                            onClick={() => pdfMutation.mutate(b)}
                            disabled={pdfDownloadingId === b.id}
                            className="flex items-center gap-1.5 text-on-surface-variant font-semibold text-body-sm hover:text-on-surface disabled:opacity-50"
                            title="تحميل تأكيد الحجز PDF"
                          >
                            {pdfDownloadingId === b.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <FileDown className="w-3.5 h-3.5" />
                            )}{" "}
                            PDF
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
