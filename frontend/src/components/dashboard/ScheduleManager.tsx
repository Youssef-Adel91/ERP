"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Loader2, Pause, Play, Send, Trash2 } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";

interface Schedule {
  id: string;
  name: string;
  report_name: string;
  period: string;
  frequency: string;
  file_format: string;
  recipients: string[];
  is_active: boolean;
  next_run_on: string;
  last_run_at: string | null;
  last_status: string | null;
}

const FREQ: Record<string, string> = { daily: "يوميًا", weekly: "أسبوعيًا", monthly: "شهريًا" };
const PERIOD: Record<string, string> = {
  none: "بدون فترة (حسب التقرير)",
  yesterday: "أمس",
  today: "اليوم",
  last_7_days: "آخر 7 أيام",
  last_30_days: "آخر 30 يوم",
  month_to_date: "من أول الشهر",
  last_month: "الشهر الماضي",
};

const statusText = (s: string | null) => {
  if (!s) return "لم يُرسل بعد";
  if (s === "smtp_not_configured") return "البريد غير مُعدّ (SMTP)";
  if (s.startsWith("sent:")) return `تم الإرسال (${s.slice(5)})`;
  if (s === "send_failed") return "فشل الإرسال";
  return s;
};

/** Scheduled e-mailed reports — shown to OWNER/ADMIN only (the API 403s everyone else). */
export function ScheduleManager({ report }: { report: { name: string; title: string } | null }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [frequency, setFrequency] = useState("weekly");
  const [period, setPeriod] = useState("last_7_days");
  const [format, setFormat] = useState("xlsx");
  const [emails, setEmails] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["ai-schedules"],
    queryFn: async () => (await apiClient.get<{ schedules: Schedule[]; smtp_configured: boolean }>("/ai/schedules")).data,
    retry: false,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["ai-schedules"] });
  const create = useMutation({
    mutationFn: async () =>
      apiClient.post("/ai/schedules", {
        name: name.trim() || report?.title,
        report_name: report?.name,
        frequency,
        period,
        file_format: format,
        recipients: emails.split(/[,\s;]+/).filter(Boolean),
      }),
    onSuccess: () => {
      setMsg("تمت الجدولة.");
      setEmails("");
      setName("");
      refresh();
    },
    onError: (e) => setMsg(getApiErrorMessage(e, "تعذرت الجدولة.")),
  });
  const toggle = useMutation({ mutationFn: async (id: string) => apiClient.patch(`/ai/schedules/${id}/toggle`), onSuccess: refresh });
  const remove = useMutation({ mutationFn: async (id: string) => apiClient.delete(`/ai/schedules/${id}`), onSuccess: refresh });
  const runNow = useMutation({
    mutationFn: async (id: string) => (await apiClient.post<{ status: string }>(`/ai/schedules/${id}/run-now`)).data,
    onSuccess: (d) => {
      setMsg(`نتيجة الإرسال: ${statusText(d.status)}`);
      refresh();
    },
    onError: (e) => setMsg(getApiErrorMessage(e, "تعذر الإرسال.")),
  });

  // 403 for non-admin roles → hide the whole panel
  if (list.isError) return null;

  const field = "mt-0.5 w-full bg-surface-container rounded-md px-2 py-1.5 text-body-sm outline-none focus:ring-2 focus:ring-primary/40";

  return (
    <div className="rounded-lg border border-outline-variant p-3 space-y-3" dir="rtl">
      <div className="flex items-center gap-2">
        <CalendarClock className="w-4 h-4 text-primary" />
        <h3 className="text-body-sm font-semibold">تقارير مجدولة بالبريد</h3>
      </div>

      {list.data && !list.data.smtp_configured && (
        <p className="text-[11px] text-warning bg-surface-container rounded-md px-2 py-1.5">
          إعدادات البريد (SMTP) غير مفعّلة على السيرفر — الجدولة محفوظة وستُرسل تلقائيًا بمجرد تفعيلها.
        </p>
      )}

      {report ? (
        <div className="space-y-2">
          <p className="text-[11px] text-outline">جدولة التقرير المحدد: <b>{report.title}</b></p>
          <label className="block text-[11px] text-on-surface-variant">
            اسم الجدولة
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={report.title} className={field} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-[11px] text-on-surface-variant">
              التكرار
              <select value={frequency} onChange={(e) => setFrequency(e.target.value)} className={field}>
                {Object.entries(FREQ).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="block text-[11px] text-on-surface-variant">
              الصيغة
              <select value={format} onChange={(e) => setFormat(e.target.value)} className={field}>
                <option value="xlsx">Excel</option>
                <option value="csv">CSV</option>
              </select>
            </label>
          </div>
          <label className="block text-[11px] text-on-surface-variant">
            الفترة
            <select value={period} onChange={(e) => setPeriod(e.target.value)} className={field}>
              {Object.entries(PERIOD).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="block text-[11px] text-on-surface-variant">
            المستلمون (حتى 5 إيميلات، مفصولة بفاصلة)
            <input value={emails} onChange={(e) => setEmails(e.target.value)} dir="ltr" placeholder="owner@company.com" className={field} />
          </label>
          <button
            onClick={() => create.mutate()}
            disabled={create.isPending || !emails.trim()}
            className="w-full flex items-center justify-center gap-1.5 bg-primary text-on-primary rounded-md py-1.5 text-body-sm disabled:opacity-60"
          >
            {create.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CalendarClock className="w-4 h-4" />} جدولة
          </button>
        </div>
      ) : (
        <p className="text-[11px] text-outline">اختر تقريرًا من الكتالوج فوق لجدولته.</p>
      )}

      {msg && <p className="text-[11px] text-on-surface-variant">{msg}</p>}

      {(list.data?.schedules ?? []).map((s) => (
        <div key={s.id} className="rounded-md bg-surface-container p-2 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-body-sm font-medium truncate">{s.name}</p>
            <div className="flex items-center gap-1 shrink-0">
              <button title="إرسال الآن" onClick={() => runNow.mutate(s.id)} disabled={runNow.isPending} className="p-1 rounded hover:bg-surface-container-high"><Send className="w-3.5 h-3.5" /></button>
              <button title={s.is_active ? "إيقاف مؤقت" : "تشغيل"} onClick={() => toggle.mutate(s.id)} className="p-1 rounded hover:bg-surface-container-high">
                {s.is_active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              </button>
              <button title="حذف" onClick={() => remove.mutate(s.id)} className="p-1 rounded hover:bg-surface-container-high text-error"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          </div>
          <p className="text-[10px] text-outline">
            {FREQ[s.frequency] ?? s.frequency} · {PERIOD[s.period] ?? s.period} · {s.file_format.toUpperCase()} · القادم: <span dir="ltr">{s.next_run_on}</span>
            {!s.is_active && " · موقوفة"}
          </p>
          <p className="text-[10px] text-outline" dir="ltr">{s.recipients.join(", ")}</p>
          <p className="text-[10px] text-on-surface-variant">{statusText(s.last_status)}</p>
        </div>
      ))}
    </div>
  );
}
