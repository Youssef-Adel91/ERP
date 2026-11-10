"use client";

import { useState } from "react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Download, FileSpreadsheet, FileText, Printer, ChevronDown, ChevronUp, Loader2 } from "lucide-react";

export interface ReportColumn {
  key: string;
  label: string;
  type: "text" | "money" | "number" | "date" | "percent";
}
export interface ReportTableData {
  title: string;
  period?: { from: string; to: string } | null;
  summary: Record<string, string | number>;
  columns: ReportColumn[];
  rows: Record<string, string | number | null>[];
  count?: number;
  source?: string;
}

const fmt = (v: unknown, type: ReportColumn["type"]) => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") {
    if (type === "percent") return `${v.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
    if (type === "money") return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return String(v);
};

const fmtSummary = (v: string | number) =>
  typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : String(v);

/** Browser print → "Save as PDF". Done client-side so Arabic shaping/RTL are native. */
export function printReport(t: ReportTableData) {
  const w = window.open("", "_blank", "width=900,height=700");
  if (!w) return;
  const esc = (s: unknown) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
  const head = t.columns.map((c) => `<th>${esc(c.label)}</th>`).join("");
  const body = t.rows
    .map((r) => `<tr>${t.columns.map((c) => `<td>${esc(fmt(r[c.key], c.type))}</td>`).join("")}</tr>`)
    .join("");
  const sum = Object.entries(t.summary || {})
    .map(([k, v]) => `<div class="s"><span>${esc(k)}</span><b>${esc(fmtSummary(v))}</b></div>`)
    .join("");
  w.document.write(`<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>${esc(t.title)}</title>
<style>body{font-family:Tahoma,Arial,sans-serif;padding:24px;color:#111}h1{font-size:20px;margin:0 0 4px}.p{color:#555;font-size:12px;margin-bottom:12px}
.sum{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.s{border:1px solid #ddd;border-radius:8px;padding:6px 10px;font-size:12px}.s span{display:block;color:#666}
table{width:100%;border-collapse:collapse;font-size:12px}th{background:#1f3a5f;color:#fff;padding:6px}td{border-bottom:1px solid #e5e5e5;padding:5px 6px}
tr:nth-child(even) td{background:#f7f7f7}.f{margin-top:16px;color:#777;font-size:11px}</style></head><body>
<h1>${esc(t.title)}</h1><div class="p">${t.period ? `الفترة: ${esc(t.period.from)} ← ${esc(t.period.to)} — ` : ""}صدر في ${new Date().toLocaleString("en-US")}</div>
<div class="sum">${sum}</div><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
<div class="f">${esc(t.source || "")} — Trust Core</div><script>window.onload=()=>setTimeout(()=>window.print(),300)</script></body></html>`);
  w.document.close();
}

export async function downloadReport(name: string, params: Record<string, unknown> | null | undefined, format: "xlsx" | "csv") {
  const res = await apiClient.post("/ai/reports/export", { name, params: params ?? {}, format }, { responseType: "blob" });
  const cd = (res.headers?.["content-disposition"] as string | undefined) ?? "";
  const m = /filename="?([^";]+)"?/.exec(cd);
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = m?.[1] ?? `${name}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function ReportTable({
  table,
  reportName,
  params,
  defaultOpen = false,
}: {
  table: ReportTableData;
  reportName: string;
  params?: Record<string, unknown> | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const rows = open ? table.rows : table.rows.slice(0, 5);

  const dl = async (f: "xlsx" | "csv") => {
    setBusy(f);
    setErr(null);
    try {
      await downloadReport(reportName, params, f);
    } catch (e) {
      setErr(getApiErrorMessage(e, "تعذر تنزيل التقرير."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mt-2 rounded-lg border border-outline-variant bg-surface-container-lowest overflow-hidden" dir="rtl">
      <div className="px-3 py-2 flex items-center justify-between gap-2 border-b border-outline-variant bg-surface-container-low">
        <div className="min-w-0">
          <p className="text-body-sm font-semibold truncate">{table.title}</p>
          {table.period && (
            <p className="text-[10px] text-outline" dir="ltr">
              {table.period.from} → {table.period.to}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => dl("xlsx")} disabled={!!busy} className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-primary text-on-primary disabled:opacity-60" title="تنزيل Excel">
            {busy === "xlsx" ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileSpreadsheet className="w-3 h-3" />} Excel
          </button>
          <button onClick={() => dl("csv")} disabled={!!busy} className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-surface-container hover:bg-surface-container-high disabled:opacity-60" title="تنزيل CSV">
            {busy === "csv" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />} CSV
          </button>
          <button onClick={() => printReport(table)} className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-surface-container hover:bg-surface-container-high" title="طباعة / حفظ PDF">
            <Printer className="w-3 h-3" /> PDF
          </button>
        </div>
      </div>

      {Object.keys(table.summary || {}).length > 0 && (
        <div className="p-2 grid grid-cols-2 md:grid-cols-3 gap-2">
          {Object.entries(table.summary).map(([k, v]) => (
            <div key={k} className="rounded-md bg-surface-container px-2 py-1.5">
              <p className="text-[10px] text-outline">{k}</p>
              <p className="text-body-sm font-semibold">{fmtSummary(v)}</p>
            </div>
          ))}
        </div>
      )}

      {table.rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="bg-surface-container-low text-on-surface-variant">
                {table.columns.map((c) => (
                  <th key={c.key} className="px-2 py-1.5 text-right font-medium whitespace-nowrap">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-outline-variant/50 hover:bg-surface-container-low/60">
                  {table.columns.map((c) => (
                    <td key={c.key} className={`px-2 py-1.5 whitespace-nowrap ${c.type === "money" || c.type === "number" ? "tabular-nums" : ""}`}>
                      {fmt(r[c.key], c.type)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-3 text-body-sm text-outline">لا توجد صفوف في هذه الفترة.</p>
      )}

      {table.rows.length > 5 && (
        <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-center gap-1 text-[11px] py-1.5 text-primary hover:bg-surface-container-low">
          {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {open ? "إخفاء" : `عرض كل الصفوف (${table.rows.length})`}
        </button>
      )}
      {err && <p className="px-3 py-1.5 text-[11px] text-error">{err}</p>}
      {table.source && (
        <p className="px-3 py-1 text-[10px] text-outline border-t border-outline-variant/50 flex items-center gap-1">
          <FileText className="w-3 h-3" /> {table.source}
        </p>
      )}
    </div>
  );
}
