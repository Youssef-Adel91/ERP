"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiClient, getApiErrorMessage, getAccessToken } from "@/lib/api-client";
import { useAppStore } from "@/store/use-app-store";
import { Bot, Send, Loader2, Sparkles, User as UserIcon, BookOpen, Play, Cpu, ListChecks, Trash2 } from "lucide-react";
import { ReportTable, type ReportTableData } from "@/components/dashboard/ReportTable";

interface AskResponse {
  answer: string;
  report_used: string | null;
  report_params: Record<string, unknown> | null;
  table: ReportTableData | null;
  mode: "llm" | "rules";
  suggestions: string[];
}
interface Msg {
  role: "user" | "assistant";
  text: string;
  table?: ReportTableData | null;
  report?: string | null;
  params?: Record<string, unknown> | null;
  mode?: "llm" | "rules";
  suggestions?: string[];
}
interface CatalogParam {
  key: string;
  type: string;
  label: string;
  required: boolean;
}
interface CatalogReport {
  name: string;
  title: string;
  category: string;
  description: string;
  params: CatalogParam[];
}

const STORAGE_KEY = "assistant-chat-v1";

/** Minimal markdown: **bold**, bullets, headings and pipe tables (models love tables). */
function Rich({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let i = 0;
  let n = 0;
  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*)/g).map((p, k) => (p.startsWith("**") && p.endsWith("**") ? <strong key={k}>{p.slice(2, -2)}</strong> : <span key={k}>{p}</span>));
  while (i < lines.length) {
    const l = lines[i];
    if (l.trim().startsWith("|")) {
      const block: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) block.push(lines[i++]);
      const cells = (r: string) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const rows = block.filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r)).map(cells);
      if (rows.length) {
        out.push(
          <div key={`t${n++}`} className="overflow-x-auto my-1">
            <table className="text-[12px] border border-outline-variant/60">
              <thead>
                <tr className="bg-surface-container-high">{rows[0].map((c, k) => <th key={k} className="px-2 py-1 text-right">{inline(c)}</th>)}</tr>
              </thead>
              <tbody>
                {rows.slice(1).map((r, a) => (
                  <tr key={a} className="border-t border-outline-variant/40">{r.map((c, k) => <td key={k} className="px-2 py-1">{inline(c)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
      }
      continue;
    }
    if (/^#{1,4}\s/.test(l)) out.push(<p key={`h${n++}`} className="font-semibold mt-1">{inline(l.replace(/^#{1,4}\s/, ""))}</p>);
    else if (/^\s*[-•*]\s/.test(l)) out.push(<p key={`b${n++}`} className="pr-3">• {inline(l.replace(/^\s*[-•*]\s/, ""))}</p>);
    else if (l.trim() === "") out.push(<div key={`s${n++}`} className="h-1" />);
    else out.push(<p key={`p${n++}`}>{inline(l)}</p>);
    i++;
  }
  return <div className="space-y-0.5">{out}</div>;
}

export default function AssistantPage() {
  const { user } = useAppStore();
  const router = useRouter();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // catalogue panel
  const [selected, setSelected] = useState<CatalogReport | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [direct, setDirect] = useState<{ table: ReportTableData; name: string; params: Record<string, unknown> } | null>(null);

  useEffect(() => {
    if (!user && !getAccessToken()) router.push("/login");
  }, [user, router]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) setMessages(JSON.parse(raw));
    } catch {
      /* storage unavailable — start empty */
    }
  }, []);
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-30)));
    } catch {
      /* ignore */
    }
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const { data: sugg } = useQuery({
    queryKey: ["ai-suggestions"],
    queryFn: async () => (await apiClient.get<{ suggestions: string[] }>("/ai/suggestions")).data.suggestions,
    enabled: !!user,
  });
  const { data: catalog } = useQuery({
    queryKey: ["ai-report-catalog"],
    queryFn: async () => (await apiClient.get<{ reports: CatalogReport[] }>("/ai/reports/catalog")).data.reports,
    enabled: !!user,
  });
  const grouped = useMemo(() => {
    const g: Record<string, CatalogReport[]> = {};
    (catalog ?? []).forEach((r) => (g[r.category] ||= []).push(r));
    return g;
  }, [catalog]);

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || loading) return;
    setError(null);
    setMessages((p) => [...p, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await apiClient.post<AskResponse>("/ai/ask", { question }, { timeout: 90_000 });
      setMessages((p) => [
        ...p,
        { role: "assistant", text: data.answer, table: data.table, report: data.report_used, params: data.report_params, mode: data.mode, suggestions: data.suggestions },
      ]);
    } catch (e) {
      setError(getApiErrorMessage(e, "تعذر الحصول على رد من المساعد."));
    } finally {
      setLoading(false);
    }
  };

  const pick = (r: CatalogReport) => {
    setSelected(r);
    setDirect(null);
    setForm({});
  };

  const run = async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    const params: Record<string, unknown> = {};
    selected.params.forEach((p) => {
      const v = form[p.key];
      if (v !== undefined && v !== "") params[p.key] = p.type === "integer" ? Number(v) : v;
    });
    try {
      const { data } = await apiClient.post<ReportTableData>("/ai/reports/run", { name: selected.name, params }, { timeout: 90_000 });
      setDirect({ table: data, name: selected.name, params });
    } catch (e) {
      setError(getApiErrorMessage(e, "تعذر تشغيل التقرير."));
    } finally {
      setRunning(false);
    }
  };

  if (!user) return null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-4" dir="rtl">
      {/* ───────── chat ───────── */}
      <div className="glass-card rounded-xl shadow-card flex flex-col h-[calc(100vh-150px)] min-h-[520px]">
        <div className="p-card-padding border-b border-outline-variant flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-primary-container/10 rounded-lg">
              <Sparkles className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="font-headline-sm text-headline-sm">المساعد الذكي</h1>
              <p className="text-[11px] text-outline-variant">اسأل عن أي رقم في شركتك واحصل على تقرير تقدر تنزّله Excel أو PDF</p>
            </div>
          </div>
          {messages.length > 0 && (
            <button onClick={() => setMessages([])} className="flex items-center gap-1 text-[11px] text-outline hover:text-error">
              <Trash2 className="w-3.5 h-3.5" /> مسح المحادثة
            </button>
          )}
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-body-md text-on-surface-variant">أنا مساعدك المالي. جرّب تسألني زي:</p>
              <div className="flex flex-wrap gap-2">
                {(sugg ?? []).map((s) => (
                  <button key={s} onClick={() => ask(s)} className="text-body-sm px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant">
                    {s}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-outline">أو اختار تقرير من القايمة اللي على الجنب وحدّد الفترة بنفسك.</p>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${m.role === "user" ? "bg-primary text-on-primary" : "bg-secondary-container/20 text-secondary"}`}>
                {m.role === "user" ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
              </div>
              <div className={`max-w-[88%] min-w-0 rounded-xl px-3 py-2 text-body-sm ${m.role === "user" ? "bg-primary text-on-primary rounded-tl-sm" : "bg-surface-container text-on-surface rounded-tr-sm"}`}>
                {m.role === "assistant" ? <Rich text={m.text} /> : <p className="whitespace-pre-wrap">{m.text}</p>}
                {m.table && m.report && <ReportTable table={m.table} reportName={m.report} params={m.params} defaultOpen={m.table.rows.length <= 8} />}
                {m.role === "assistant" && m.mode && (
                  <p className="text-[10px] mt-1.5 opacity-60 flex items-center gap-1">
                    <Cpu className="w-3 h-3" /> {m.mode === "llm" ? "ذكاء اصطناعي" : "محرك التقارير"}
                    {m.report && <span dir="ltr" className="font-data-mono"> · {m.report}</span>}
                  </p>
                )}
                {m.suggestions && m.suggestions.length > 0 && !m.report && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {m.suggestions.map((s) => (
                      <button key={s} onClick={() => ask(s)} className="text-[11px] px-2 py-1 rounded-full bg-surface-container-high hover:bg-surface-container-highest">
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex gap-2">
              <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-secondary-container/20 text-secondary">
                <Bot className="w-4 h-4" />
              </div>
              <div className="rounded-xl px-3 py-2 bg-surface-container flex items-center gap-2 text-body-sm text-outline">
                <Loader2 className="w-4 h-4 animate-spin" /> بجهّز التقرير من أرقامك...
              </div>
            </div>
          )}
          {error && <p className="text-body-sm text-error">{error}</p>}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="p-3 border-t border-outline-variant flex items-center gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="اكتب سؤالك... مثال: ما هي أرباحي آخر 30 يوم؟"
            className="flex-1 bg-surface-container rounded-lg px-3 py-2.5 text-body-sm outline-none focus:ring-2 focus:ring-primary/40"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()} className="bg-primary text-on-primary p-2.5 rounded-lg disabled:opacity-50 hover:opacity-90">
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* ───────── catalogue ───────── */}
      <aside className="glass-card rounded-xl shadow-card p-4 space-y-3 xl:h-[calc(100vh-150px)] xl:overflow-y-auto">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-primary" />
          <h2 className="font-headline-sm text-headline-sm">كتالوج التقارير</h2>
        </div>

        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat}>
            <p className="text-[11px] text-outline mb-1 flex items-center gap-1"><ListChecks className="w-3 h-3" /> {cat}</p>
            <div className="flex flex-wrap gap-1.5">
              {items.map((r) => (
                <button
                  key={r.name}
                  onClick={() => pick(r)}
                  className={`text-[12px] px-2.5 py-1 rounded-md border ${selected?.name === r.name ? "bg-primary text-on-primary border-primary" : "bg-surface-container border-transparent hover:bg-surface-container-high"}`}
                >
                  {r.title}
                </button>
              ))}
            </div>
          </div>
        ))}

        {selected && (
          <div className="rounded-lg border border-outline-variant p-3 space-y-2">
            <p className="text-body-sm font-semibold">{selected.title}</p>
            <p className="text-[11px] text-outline">{selected.description}</p>
            {selected.params.map((p) => (
              <label key={p.key} className="block text-[11px] text-on-surface-variant">
                {p.label}
                <input
                  type={p.key.startsWith("date") || p.key === "as_of" ? "date" : p.type === "integer" ? "number" : "text"}
                  value={form[p.key] ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, [p.key]: e.target.value }))}
                  className="mt-0.5 w-full bg-surface-container rounded-md px-2 py-1.5 text-body-sm outline-none focus:ring-2 focus:ring-primary/40"
                  dir={p.key.startsWith("date") || p.key === "as_of" ? "ltr" : "rtl"}
                />
              </label>
            ))}
            <button onClick={run} disabled={running} className="w-full flex items-center justify-center gap-1.5 bg-primary text-on-primary rounded-md py-1.5 text-body-sm disabled:opacity-60">
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} تشغيل التقرير
            </button>
          </div>
        )}

        {direct && <ReportTable table={direct.table} reportName={direct.name} params={direct.params} defaultOpen />}
      </aside>
    </div>
  );
}
