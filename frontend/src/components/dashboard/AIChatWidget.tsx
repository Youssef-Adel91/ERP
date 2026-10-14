"use client";

import { useState, useRef, useEffect } from "react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Sparkles, Send, Loader2, Bot, User as UserIcon } from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  reportUsed?: string | null;
}

interface AskResponse {
  answer: string;
  report_used: string | null;
}

const SUGGESTIONS = [
  "إيه إجمالي الإيرادات والمديونيات؟",
  "ليه الإيرادات اتغيرت عن الشهر اللي فات؟",
  "مين أكبر العملاء عندي؟",
  "فيه فواتير متأخرة عن السداد؟",
];

/**
 * AIChatWidget — an in-dashboard front door to the same Copilot
 * (POST /ai/ask → app.modules.ai.service.answer_question) already
 * live-verified over WhatsApp (Level 1 grounded retrieval + Level 2
 * variance analysis). Nothing new on the backend — this is Phase B's
 * "put the AI Bot where the merchant is already looking" surface: the
 * dashboard, not just WhatsApp.
 *
 * Every answer is grounded in REPORT_REGISTRY (real numbers from the
 * ledger); report_used is shown as a small drill-through tag so the
 * merchant can see which report backed the answer, same transparency
 * guarantee as the WhatsApp channel.
 */
export function AIChatWidget() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || loading) return;
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await apiClient.post<AskResponse>("/ai/ask", { question: q });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.answer, reportUsed: data.report_used },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر الحصول على رد من المساعد الذكي."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card rounded-xl shadow-card flex flex-col h-[420px]" dir="rtl">
      <div className="p-card-padding border-b border-outline-variant flex items-center gap-2">
        <div className="p-2 bg-primary-container/10 rounded-lg">
          <Sparkles className="w-4 h-4 text-primary" />
        </div>
        <div>
          <h4 className="font-headline-sm text-headline-sm">اسأل المساعد الذكي</h4>
          <p className="text-[10px] text-outline-variant">إجابات مبنية على أرقامك الحقيقية فقط</p>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-body-sm text-on-surface-variant">جرّب تسأل حاجة زي:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="text-body-sm px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high transition-colors text-on-surface-variant"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <div
              className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                m.role === "user" ? "bg-primary text-on-primary" : "bg-secondary-container/20 text-secondary"
              }`}
            >
              {m.role === "user" ? <UserIcon className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
            </div>
            <div
              className={`max-w-[80%] rounded-xl px-3 py-2 text-body-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-primary text-on-primary rounded-tl-sm"
                  : "bg-surface-container text-on-surface rounded-tr-sm"
              }`}
            >
              {m.text}
              {m.reportUsed && (
                <p className="text-[10px] mt-1.5 opacity-70 font-data-mono" dir="ltr">
                  drill-through: {m.reportUsed}
                </p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-2">
            <div className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-secondary-container/20 text-secondary">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="rounded-xl px-3 py-2 bg-surface-container">
              <Loader2 className="w-4 h-4 animate-spin text-outline" />
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
          placeholder="اكتب سؤالك عن أرقام شركتك..."
          className="flex-1 bg-surface-container rounded-lg px-3 py-2 text-body-sm outline-none focus:ring-2 focus:ring-primary/40"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-primary text-on-primary p-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
