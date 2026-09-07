"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { apiClient, getApiErrorMessage, pickDetail } from "@/lib/api-client";
import { AxiosError } from "axios";
import {
  Truck,
  Loader2,
  AlertCircle,
  Search,
  Upload,
  X,
  CheckCircle2,
  FileText,
} from "lucide-react";

type SettlementState = "imported" | "matched" | "partially_matched" | "posted" | "disputed";
type LineMatchState = "matched" | "fuzzy_matched" | "unmatched" | "disputed";
type LineExceptionType =
  | "none"
  | "remitted_but_not_delivered"
  | "amount_mismatch"
  | "unknown_awb"
  | "duplicate_settlement";

interface Settlement {
  id: string;
  carrier_code: string;
  settlement_ref: string;
  gross_amount: string | number;
  total_fees: string | number;
  net_amount: string | number;
  state: SettlementState;
  created_at: string;
  posted_at?: string | null;
  journal_entry_id?: string | null;
}

interface SettlementLine {
  id: string;
  awb_number: string;
  cod_collected: string | number;
  shipping_fee: string | number;
  cod_fee: string | number;
  return_fee: string | number;
  net_remitted: string | number;
  match_state: LineMatchState;
  exception_type: LineExceptionType;
  shipment_id: string | null;
  notes: string;
}

interface SettlementDetail {
  settlement: Settlement;
  lines: SettlementLine[];
}

interface AgingSnapshot {
  carrier_code: string;
  [key: string]: unknown;
}

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const stateLabel: Record<SettlementState, string> = {
  imported: "مستوردة",
  matched: "مطابقة بالكامل",
  partially_matched: "مطابقة جزئيًا",
  posted: "مرحّلة",
  disputed: "متنازع عليها",
};
const stateTone: Record<SettlementState, string> = {
  imported: "bg-surface-container text-on-surface-variant",
  matched: "bg-secondary-container/30 text-secondary",
  partially_matched: "bg-primary-container/10 text-primary",
  posted: "bg-tertiary-container/10 text-tertiary",
  disputed: "bg-error-container text-on-error-container",
};

const matchStateLabel: Record<LineMatchState, string> = {
  matched: "مطابقة",
  fuzzy_matched: "مطابقة تقريبية",
  unmatched: "غير مطابقة",
  disputed: "متنازع عليها",
};
const matchStateTone: Record<LineMatchState, string> = {
  matched: "bg-secondary-container/30 text-secondary",
  fuzzy_matched: "bg-primary-container/10 text-primary",
  unmatched: "bg-warning-bg text-warning",
  disputed: "bg-error-container text-on-error-container",
};

const exceptionLabel: Record<LineExceptionType, string> = {
  none: "—",
  remitted_but_not_delivered: "محصّلة قبل التسليم",
  amount_mismatch: "فرق في المبلغ",
  unknown_awb: "بوليصة غير معروفة",
  duplicate_settlement: "تسوية مكررة",
};

// Settlements can be reconciled/committed from a settlement whose header lives
// inside a `.glass-card` row (backdrop-filter creates a new stacking context
// and containing block for `position: fixed` descendants — confirmed live via
// document.elementFromPoint() while building the POS refund modal). Both
// modals below render via createPortal(..., document.body) to avoid getting
// trapped beneath later same-level DOM siblings despite a high z-index.

function UploadSettlementModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (settlementId: string) => void;
}) {
  const [mode, setMode] = useState<"file" | "json">("file");
  const [carrierCode, setCarrierCode] = useState("");
  const [settlementRef, setSettlementRef] = useState("");
  const [tolerance, setTolerance] = useState("5");
  const [dateWindowDays, setDateWindowDays] = useState("7");
  const [file, setFile] = useState<File | null>(null);
  const [linesJson, setLinesJson] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!carrierCode.trim() || !settlementRef.trim()) {
      setError("من فضلك أدخل كود شركة الشحن ومرجع التسوية.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      if (mode === "file") {
        if (!file) {
          setError("من فضلك اختر ملف الكشف (CSV أو JSON).");
          setSubmitting(false);
          return;
        }
        const formData = new FormData();
        formData.append("file", file);
        formData.append("carrier_code", carrierCode.trim());
        formData.append("settlement_ref", settlementRef.trim());
        formData.append("tolerance", tolerance || "5");
        formData.append("date_window_days", dateWindowDays || "7");
        const { data } = await apiClient.post<Settlement>("/finance/settlements/upload", formData);
        onCreated(data.id);
      } else {
        let parsedLines: unknown;
        try {
          parsedLines = JSON.parse(linesJson || "[]");
        } catch {
          setError("صيغة JSON غير صحيحة لسطور الكشف.");
          setSubmitting(false);
          return;
        }
        if (!Array.isArray(parsedLines)) {
          setError("يجب أن تكون سطور الكشف مصفوفة (array).");
          setSubmitting(false);
          return;
        }
        const { data } = await apiClient.post<Settlement>("/finance/settlements/match-json", {
          carrier_code: carrierCode.trim(),
          settlement_ref: settlementRef.trim(),
          lines: parsedLines,
          tolerance: Number(tolerance || "5"),
          date_window_days: Number(dateWindowDays || "7"),
        });
        onCreated(data.id);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر مطابقة كشف التسوية."));
    } finally {
      setSubmitting(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="glass-card w-full max-w-lg rounded-xl p-card-padding max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">تسوية كشف شركة شحن جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setMode("file")}
            className={`flex-1 py-2 rounded-lg text-body-sm font-semibold transition-colors ${mode === "file" ? "bg-primary text-on-primary" : "bg-surface-container-low text-on-surface-variant"}`}
          >
            رفع ملف (CSV / JSON)
          </button>
          <button
            onClick={() => setMode("json")}
            className={`flex-1 py-2 rounded-lg text-body-sm font-semibold transition-colors ${mode === "json" ? "bg-primary text-on-primary" : "bg-surface-container-low text-on-surface-variant"}`}
          >
            إدخال يدوي (JSON)
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-body-sm text-on-surface-variant block mb-1">كود شركة الشحن</label>
            <input
              value={carrierCode}
              onChange={(e) => setCarrierCode(e.target.value)}
              placeholder="bosta"
              dir="ltr"
              className="w-full px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg text-body-md outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary font-mono"
            />
          </div>
          <div>
            <label className="text-body-sm text-on-surface-variant block mb-1">مرجع التسوية</label>
            <input
              value={settlementRef}
              onChange={(e) => setSettlementRef(e.target.value)}
              placeholder="SET-2026-001"
              dir="ltr"
              className="w-full px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg text-body-md outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary font-mono"
            />
          </div>
          <div>
            <label className="text-body-sm text-on-surface-variant block mb-1">هامش تسامح المبلغ</label>
            <input
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
              type="number"
              step="0.01"
              dir="ltr"
              className="w-full px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg text-body-md outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary font-mono"
            />
          </div>
          <div>
            <label className="text-body-sm text-on-surface-variant block mb-1">نطاق المطابقة (أيام)</label>
            <input
              value={dateWindowDays}
              onChange={(e) => setDateWindowDays(e.target.value)}
              type="number"
              dir="ltr"
              className="w-full px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg text-body-md outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary font-mono"
            />
          </div>
        </div>

        {mode === "file" ? (
          <div className="mb-4">
            <label className="text-body-sm text-on-surface-variant block mb-1">ملف الكشف (CSV أو JSON)</label>
            <input
              type="file"
              accept=".csv,.json,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full text-body-sm file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-primary-container/20 file:text-primary file:font-semibold"
            />
          </div>
        ) : (
          <div className="mb-4">
            <label className="text-body-sm text-on-surface-variant block mb-1">سطور الكشف (JSON array)</label>
            <textarea
              value={linesJson}
              onChange={(e) => setLinesJson(e.target.value)}
              rows={6}
              dir="ltr"
              placeholder={'[{"awb_number":"12345","cod_collected":250,"shipping_fee":20,"cod_fee":5,"return_fee":0,"phone_tail":"1234"}]'}
              className="w-full px-3 py-2 bg-surface-container-low border border-outline-variant rounded-lg text-body-sm outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary font-mono"
            />
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error mb-4">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-lg text-body-md font-semibold bg-surface-container-low text-on-surface-variant hover:bg-surface-container transition-colors"
          >
            إلغاء
          </button>
          <button
            onClick={submit}
            disabled={submitting}
            className="flex-1 py-2.5 rounded-lg text-body-md font-semibold bg-primary text-on-primary hover:opacity-90 transition-opacity disabled:opacity-70 flex items-center justify-center gap-2"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {submitting ? "جاري المطابقة..." : "مطابقة الآن"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function SettlementDetailModal({
  settlementId,
  onClose,
  onPosted,
}: {
  settlementId: string;
  onClose: () => void;
  onPosted: () => void;
}) {
  const [detail, setDetail] = useState<SettlementDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [posting, setPosting] = useState(false);
  const [postError, setPostError] = useState("");
  const [postResult, setPostResult] = useState<{ journal_entry_id: string } | null>(null);

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<SettlementDetail>(`/finance/settlements/${settlementId}`);
      setDetail(data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل تفاصيل التسوية."));
    } finally {
      setLoading(false);
    }
  }, [settlementId]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  const commitToGl = async () => {
    setPosting(true);
    setPostError("");
    try {
      const { data } = await apiClient.post<{ status: string; journal_entry_id: string }>(
        `/finance/settlements/${settlementId}/commit`,
      );
      setPostResult({ journal_entry_id: data.journal_entry_id });
      await fetchDetail();
      onPosted();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setPostError(pickDetail(axiosErr, "تعذر ترحيل التسوية إلى دفتر الأستاذ."));
    } finally {
      setPosting(false);
    }
  };

  const canCommit = detail && (detail.settlement.state === "matched" || detail.settlement.state === "partially_matched");

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-4">
      <div className="glass-card w-full max-w-3xl rounded-xl p-card-padding max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">تفاصيل التسوية</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : error ? (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>
        ) : detail ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <div className="bg-surface-container-low rounded-lg p-3">
                <div className="text-body-sm text-on-surface-variant">شركة الشحن</div>
                <div className="font-bold font-mono" dir="ltr">{detail.settlement.carrier_code}</div>
              </div>
              <div className="bg-surface-container-low rounded-lg p-3">
                <div className="text-body-sm text-on-surface-variant">المرجع</div>
                <div className="font-bold font-mono" dir="ltr">{detail.settlement.settlement_ref}</div>
              </div>
              <div className="bg-surface-container-low rounded-lg p-3">
                <div className="text-body-sm text-on-surface-variant">الصافي</div>
                <div className="font-bold font-data-mono" dir="ltr">{egp(detail.settlement.net_amount)}</div>
              </div>
              <div className="bg-surface-container-low rounded-lg p-3">
                <div className="text-body-sm text-on-surface-variant">الحالة</div>
                <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${stateTone[detail.settlement.state]}`}>{stateLabel[detail.settlement.state]}</span>
              </div>
            </div>

            <div className="overflow-x-auto mb-4 rounded-lg border border-outline-variant/30">
              <table className="w-full text-right text-body-sm">
                <thead className="bg-surface-container-low text-outline font-bold border-b border-outline-variant">
                  <tr>
                    <th className="px-4 py-3">بوليصة الشحن</th>
                    <th className="px-4 py-3">المحصّل</th>
                    <th className="px-4 py-3">الرسوم</th>
                    <th className="px-4 py-3">الصافي</th>
                    <th className="px-4 py-3">المطابقة</th>
                    <th className="px-4 py-3">الاستثناء</th>
                    <th className="px-4 py-3">ملاحظات</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30">
                  {detail.lines.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-on-surface-variant">لا توجد سطور في هذا الكشف.</td></tr>
                  ) : (
                    detail.lines.map((line) => (
                      <tr key={line.id}>
                        <td className="px-4 py-3 font-mono" dir="ltr">{line.awb_number}</td>
                        <td className="px-4 py-3 font-data-mono" dir="ltr">{egp(line.cod_collected)}</td>
                        <td className="px-4 py-3 font-data-mono text-error" dir="ltr">
                          {egp(Number(line.shipping_fee) + Number(line.cod_fee) + Number(line.return_fee))}
                        </td>
                        <td className="px-4 py-3 font-data-mono font-bold" dir="ltr">{egp(line.net_remitted)}</td>
                        <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded text-[11px] font-bold ${matchStateTone[line.match_state]}`}>{matchStateLabel[line.match_state]}</span></td>
                        <td className="px-4 py-3 text-on-surface-variant">{exceptionLabel[line.exception_type]}</td>
                        <td className="px-4 py-3 text-on-surface-variant max-w-[220px] truncate" title={line.notes}>{line.notes || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {postError && (
              <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error mb-3">
                <AlertCircle className="w-4 h-4 shrink-0" /> {postError}
              </div>
            )}

            {postResult && (
              <div className="flex items-center gap-2 bg-secondary-container/30 text-secondary p-3 rounded-lg text-body-sm font-medium mb-3">
                <CheckCircle2 className="w-4 h-4 shrink-0" /> تم الترحيل بنجاح — قيد اليومية رقم {postResult.journal_entry_id.slice(0, 8)}
              </div>
            )}

            {detail.settlement.state === "posted" ? (
              <div className="flex items-center gap-2 bg-tertiary-container/10 text-tertiary p-3 rounded-lg text-body-sm font-medium">
                <CheckCircle2 className="w-4 h-4 shrink-0" /> هذه التسوية مرحّلة بالفعل إلى دفتر الأستاذ.
              </div>
            ) : canCommit ? (
              <button
                onClick={commitToGl}
                disabled={posting}
                className="w-full py-2.5 rounded-lg text-body-md font-semibold bg-primary text-on-primary hover:opacity-90 transition-opacity disabled:opacity-70 flex items-center justify-center gap-2"
              >
                {posting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {posting ? "جاري الترحيل..." : "ترحيل إلى دفتر الأستاذ"}
              </button>
            ) : (
              <div className="flex items-center gap-2 bg-warning-bg text-warning p-3 rounded-lg text-body-sm font-medium">
                <AlertCircle className="w-4 h-4 shrink-0" /> لا يمكن الترحيل إلا للتسويات المطابقة كليًا أو جزئيًا.
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

export default function SettlementsPage() {
  const [settlements, setSettlements] = useState<Settlement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [carrierCode, setCarrierCode] = useState("");
  const [aging, setAging] = useState<AgingSnapshot | null>(null);
  const [agingLoading, setAgingLoading] = useState(false);
  const [agingError, setAgingError] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [selectedSettlementId, setSelectedSettlementId] = useState<string | null>(null);

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
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">تسويات شركات الشحن (COD)</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">مطابقة تحصيلات الدفع عند الاستلام مع كشوف شركات الشحن.</p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="bg-primary text-on-primary px-4 py-2.5 rounded-lg text-body-md font-semibold hover:opacity-90 transition-opacity flex items-center gap-2"
        >
          <FileText className="w-4 h-4" /> تسوية كشف جديد
        </button>
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
                  <tr
                    key={s.id}
                    onClick={() => setSelectedSettlementId(s.id)}
                    className="hover:bg-surface-container-lowest transition-colors cursor-pointer"
                  >
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

      {showUpload && (
        <UploadSettlementModal
          onClose={() => setShowUpload(false)}
          onCreated={(settlementId) => {
            setShowUpload(false);
            fetchAll();
            setSelectedSettlementId(settlementId);
          }}
        />
      )}

      {selectedSettlementId && (
        <SettlementDetailModal
          settlementId={selectedSettlementId}
          onClose={() => setSelectedSettlementId(null)}
          onPosted={fetchAll}
        />
      )}
    </div>
  );
}
