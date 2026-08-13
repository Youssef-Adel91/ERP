"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, getApiErrorMessage, pickDetail } from "@/lib/api-client";
import { AxiosError } from "axios";
import { Truck, Loader2, AlertCircle, Search } from "lucide-react";

type SettlementState = "imported" | "matched" | "partially_matched" | "posted";

interface Settlement {
  id: string;
  carrier_code: string;
  settlement_ref: string;
  gross_amount: string | number;
  total_fees: string | number;
  net_amount: string | number;
  state: SettlementState;
  created_at: string;
}

interface AgingSnapshot {
  carrier_code: string;
  [key: string]: unknown;
}

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;
const stateLabel: Record<SettlementState, string> = { imported: "مستوردة", matched: "مطابقة بالكامل", partially_matched: "مطابقة جزئيًا", posted: "مرحّلة" };
const stateTone: Record<SettlementState, string> = {
  imported: "bg-surface-container text-on-surface-variant",
  matched: "bg-secondary-container/30 text-secondary",
  partially_matched: "bg-primary-container/10 text-primary",
  posted: "bg-tertiary-container/10 text-tertiary",
};

export default function SettlementsPage() {
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [carrierCode, setCarrierCode] = useState("");
  const [aging, setAging] = useState<AgingSnapshot | null>(null);
  const [agingLoading, setAgingLoading] = useState(false);
  const [agingError, setAgingError] = useState("");

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<Settlement[]>("/finance/settlements");
      setSettlements(data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل تسويات شركات الشحن."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const lookupAging = async () => {
    if (!carrierCode.trim()) return;
    setAgingLoading(true);
    setAging(null);
    setAgingError("");
    try {
      const { data } = await apiClient.get<AgingSnapshot>(`/finance/settlements/aging/${carrierCode.trim()}`);
      setAging(data);
    } catch (err) {
      // Kept separate from the main settlements-list `error` state — a
      // failed aging lookup previously wrote into that same state, which
      // made the whole settlements table render as if it had failed to
      // load, even though it hadn't.
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setAgingError(pickDetail(axiosErr, "تعذر جلب تقرير الأعمار لهذه الشركة."));
    } finally {
      setAgingLoading(false);
    }
  };

  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">تسويات شركات الشحن (COD)</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">مطابقة تحصيلات الدفع عند الاستلام مع كشوف شركات الشحن.</p>
      </div>

      {error && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>}

      <div className="glass-card rounded-xl p-4 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-outline" />
          <input
            value={carrierCode}
            onChange={(e) => setCarrierCode(e.target.value)}
            placeholder="كود شركة الشحن (مثال: bosta)"
            dir="ltr"
            className="w-full pr-9 pl-4 py-2.5 bg-surface-container-low border border-outline-variant rounded-lg text-body-md outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-right font-mono"
          />
        </div>
        <button onClick={lookupAging} disabled={agingLoading} className="bg-primary text-on-primary px-4 py-2.5 rounded-lg text-body-md font-semibold hover:opacity-90 transition-opacity disabled:opacity-70 w-full sm:w-auto">
          {agingLoading ? "جاري البحث..." : "عرض أعمار الذمم"}
        </button>
      </div>

      {agingError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {agingError}
        </div>
      )}

      {aging && (
        <div className="glass-card rounded-xl p-card-padding">
          <h4 className="font-headline-sm text-headline-sm text-on-surface mb-3">تقرير أعمار الذمم — {aging.carrier_code}</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-right text-body-sm">
              <tbody className="divide-y divide-outline-variant/30">
                {Object.entries(aging)
                  .filter(([key]) => key !== "carrier_code")
                  .map(([key, value]) => (
                    <tr key={key}>
                      <td className="py-2 pl-4 text-on-surface-variant">{key}</td>
                      <td className="py-2 font-data-mono" dir="ltr">
                        {typeof value === "object" ? JSON.stringify(value) : String(value)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : settlements.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><Truck className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد تسويات مرفوعة بعد.</p></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr><th className="px-6 py-4">شركة الشحن</th><th className="px-6 py-4">المرجع</th><th className="px-6 py-4">الإجمالي</th><th className="px-6 py-4">الرسوم</th><th className="px-6 py-4">الصافي</th><th className="px-6 py-4">الحالة</th></tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {settlements.map((s) => (
                  <tr key={s.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-medium">{s.carrier_code}</td>
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{s.settlement_ref}</td>
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{egp(s.gross_amount)}</td>
                    <td className="px-6 py-4 font-data-mono text-error" dir="ltr">{egp(s.total_fees)}</td>
                    <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">{egp(s.net_amount)}</td>
                    <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${stateTone[s.state]}`}>{stateLabel[s.state]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
