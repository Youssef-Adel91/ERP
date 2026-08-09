"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient } from "@/lib/api-client";
import {
  Receipt,
  Settings2,
  Loader2,
  AlertCircle,
  CheckCircle2,
  FileSearch,
  Tags,
  Eye,
  EyeOff,
  X,
} from "lucide-react";

// ── Types (mirrors backend app/modules/eta/api/config.py) ────────────────────

type EtaEnvironment = "PREPRODUCTION" | "PRODUCTION";
type EtaSigningProvider = "CLOUD_HSM" | "LOCAL_AGENT";
type EtaDocumentState =
  | "DRAFT" | "READY" | "QUEUED" | "SIGNING" | "SIGNED" | "SUBMITTING" | "SUBMITTED"
  | "SUBMIT_FAILED" | "RATE_DEFERRED" | "SUBMIT_UNCERTAIN" | "ACCEPTED" | "REJECTED"
  | "INVALID" | "CANCELLED";

interface EtaTenantConfig {
  id: string;
  environment: EtaEnvironment;
  client_id: string;
  client_secret_ref: string | null;
  taxpayer_rin: string;
  activity_code: string;
  signing_provider: EtaSigningProvider;
  preflight_state: string;
  is_live: boolean;
}

interface EtaDocument {
  id: string;
  internal_doc_type: string;
  internal_doc_id: string;
  eta_document_type: string;
  uuid: string | null;
  long_id: string | null;
  submission_uuid: string | null;
  state: EtaDocumentState;
  attempts: number;
  submitted_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  public_url: string | null;
  created_at: string;
}

interface EgsCode {
  id: string;
  item_id: string;
  code_type: "EGS" | "GS1";
  code_value: string;
  name_ar: string | null;
  name_en: string | null;
  is_active: boolean;
}

const docStateMeta: Record<EtaDocumentState, string> = {
  DRAFT: "bg-surface-container text-on-surface-variant",
  READY: "bg-primary-container/10 text-primary",
  QUEUED: "bg-primary-container/10 text-primary",
  SIGNING: "bg-warning-bg text-warning",
  SIGNED: "bg-primary-container/10 text-primary",
  SUBMITTING: "bg-warning-bg text-warning",
  SUBMITTED: "bg-primary-container/10 text-primary",
  SUBMIT_FAILED: "bg-error-container text-on-error-container",
  RATE_DEFERRED: "bg-warning-bg text-warning",
  SUBMIT_UNCERTAIN: "bg-warning-bg text-warning",
  ACCEPTED: "bg-success-bg text-success",
  REJECTED: "bg-error-container text-on-error-container",
  INVALID: "bg-error-container text-on-error-container",
  CANCELLED: "bg-surface-container text-on-surface-variant",
};

export default function EtaPage() {
  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الفاتورة الإلكترونية (ETA)</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          إعداد التكامل مع منظومة الفاتورة الإلكترونية المصرية، ومتابعة حالة المستندات المرسلة.
        </p>
      </div>

      <ConfigCard />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter items-start">
        <DocumentsCard />
        <EgsCodesCard />
      </div>
    </div>
  );
}

// ── ETA Config ─────────────────────────────────────────────────────────────────

const configSchema = z.object({
  environment: z.enum(["PREPRODUCTION", "PRODUCTION"]),
  client_id: z.string().min(1, "معرّف العميل مطلوب"),
  client_secret_ref: z.string().optional(),
  taxpayer_rin: z.string().min(1, "الرقم الضريبي مطلوب"),
  activity_code: z.string().min(1, "كود النشاط مطلوب"),
  signing_provider: z.enum(["CLOUD_HSM", "LOCAL_AGENT"]),
});
type ConfigForm = z.infer<typeof configSchema>;

function ConfigCard() {
  const queryClient = useQueryClient();
  const [showSecret, setShowSecret] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const { data: config, isLoading } = useQuery({
    queryKey: ["eta-config"],
    queryFn: async () => {
      const res = await apiClient.get<EtaTenantConfig | null>("/eta/config");
      return res.data;
    },
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<ConfigForm>({
    resolver: zodResolver(configSchema),
    defaultValues: {
      environment: "PREPRODUCTION",
      client_id: "",
      client_secret_ref: "",
      taxpayer_rin: "",
      activity_code: "",
      signing_provider: "CLOUD_HSM",
    },
  });

  useEffect(() => {
    if (config) {
      reset({
        environment: config.environment,
        client_id: config.client_id,
        client_secret_ref: config.client_secret_ref ?? "",
        taxpayer_rin: config.taxpayer_rin,
        activity_code: config.activity_code,
        signing_provider: config.signing_provider,
      });
    }
  }, [config, reset]);

  const mutation = useMutation({
    mutationFn: async (data: ConfigForm) => {
      await apiClient.put("/eta/config", { ...data, branch_eta_codes: {} });
    },
    onSuccess: () => {
      setErrorMsg("");
      setSuccessMsg("تم حفظ إعدادات الفاتورة الإلكترونية بنجاح.");
      queryClient.invalidateQueries({ queryKey: ["eta-config"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setSuccessMsg("");
      setErrorMsg(err.response?.data?.detail || "تعذر حفظ الإعدادات.");
    },
  });

  const onSubmit = (data: ConfigForm) => mutation.mutate(data);

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
            <Settings2 className="w-4 h-4" />
          </div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">إعدادات الاتصال بمصلحة الضرائب</h2>
        </div>
        {config && (
          <span className={`px-2 py-1 rounded text-[11px] font-bold ${config.is_live ? "bg-success-bg text-success" : "bg-surface-container text-on-surface-variant"}`}>
            {config.is_live ? "مُفعّل" : "غير مُفعّل بعد"}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">البيئة</label>
              <select {...register("environment")} className="input-field">
                <option value="PREPRODUCTION">بيئة الاختبار (Preproduction)</option>
                <option value="PRODUCTION">بيئة الإنتاج (Production)</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">مزوّد التوقيع</label>
              <select {...register("signing_provider")} className="input-field">
                <option value="CLOUD_HSM">Cloud HSM</option>
                <option value="LOCAL_AGENT">Local Agent</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">معرّف العميل (Client ID)</label>
              <input {...register("client_id")} dir="ltr" className="input-field font-mono" />
              {errors.client_id && <p className="text-body-sm text-error">{errors.client_id.message}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">
                مرجع السر في الخزنة (Vault Secret Ref)
              </label>
              <div className="relative">
                <input
                  {...register("client_secret_ref")}
                  dir="ltr"
                  type={showSecret ? "text" : "password"}
                  placeholder="vault://secrets/eta/..."
                  className="input-field font-mono pl-10"
                />
                <button
                  type="button"
                  onClick={() => setShowSecret((s) => !s)}
                  className="absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors"
                >
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-body-sm text-outline">
                هذا مرجع فقط — السر الفعلي يُخزَّن في الخزنة الآمنة (Vault) ولا يُحفظ أبدًا في قاعدة البيانات.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الرقم الضريبي (RIN)</label>
              <input {...register("taxpayer_rin")} dir="ltr" className="input-field font-mono" />
              {errors.taxpayer_rin && <p className="text-body-sm text-error">{errors.taxpayer_rin.message}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">كود النشاط التجاري</label>
              <input {...register("activity_code")} dir="ltr" className="input-field font-mono" />
              {errors.activity_code && <p className="text-body-sm text-error">{errors.activity_code.message}</p>}
            </div>
          </div>

          <button
            type="submit"
            disabled={mutation.isPending}
            className="flex items-center justify-center gap-2 h-11 px-6 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الإعدادات
          </button>
        </form>
      )}

      {successMsg && (
        <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg text-body-sm font-medium border border-success">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> {successMsg}
        </div>
      )}
      {errorMsg && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
        </div>
      )}
    </div>
  );
}

// ── Document status ────────────────────────────────────────────────────────────

function DocumentsCard() {
  const [selected, setSelected] = useState<EtaDocument | null>(null);

  const { data: documents, isLoading, isError } = useQuery({
    queryKey: ["eta-documents"],
    queryFn: async () => {
      const res = await apiClient.get<EtaDocument[]>("/eta/documents", { params: { limit: 50 } });
      return res.data;
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <FileSearch className="w-4 h-4" />
        </div>
        <div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">حالة المستندات</h2>
          <p className="text-body-sm text-on-surface-variant">
            آخر حالة مسجّلة لدينا لكل مستند (عبر إشعارات الرد من المصلحة) — وليست استعلامًا حيًّا لحظيًا.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل المستندات.
        </div>
      ) : !documents || documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-on-surface-variant gap-2">
          <Receipt className="w-7 h-7 text-outline-variant" />
          <p className="text-body-sm">لا توجد مستندات مُرسَلة بعد.</p>
        </div>
      ) : (
        <div className="divide-y divide-outline-variant/30 max-h-96 overflow-y-auto">
          {documents.map((doc) => (
            <button
              key={doc.id}
              onClick={() => setSelected(doc)}
              className="w-full flex items-center justify-between py-3 text-right hover:bg-surface-container-lowest transition-colors px-1"
            >
              <div>
                <p className="text-body-md font-medium">{doc.internal_doc_id}</p>
                <p className="text-body-sm text-outline font-data-mono" dir="ltr">{doc.internal_doc_type}</p>
              </div>
              <span className={`px-2 py-1 rounded text-[11px] font-bold ${docStateMeta[doc.state]}`}>{doc.state}</span>
            </button>
          ))}
        </div>
      )}

      {selected && <DocumentDetailModal doc={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function DocumentDetailModal({ doc, onClose }: { doc: EtaDocument; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">تفاصيل المستند</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        <DetailRow label="الحالة" value={doc.state} badge={docStateMeta[doc.state]} />
        <DetailRow label="معرّف ETA (UUID)" value={doc.uuid ?? "—"} mono />
        <DetailRow label="Long ID" value={doc.long_id ?? "—"} mono />
        <DetailRow label="معرّف الإرسال (Submission)" value={doc.submission_uuid ?? "—"} mono />
        <DetailRow label="عدد المحاولات" value={String(doc.attempts)} mono />
        <DetailRow label="تاريخ الإرسال" value={doc.submitted_at ? new Date(doc.submitted_at).toLocaleString("en-GB") : "—"} mono />
        <DetailRow label="تاريخ القبول" value={doc.accepted_at ? new Date(doc.accepted_at).toLocaleString("en-GB") : "—"} mono />
        <DetailRow label="تاريخ الرفض" value={doc.rejected_at ? new Date(doc.rejected_at).toLocaleString("en-GB") : "—"} mono />
        {doc.public_url && (
          <a href={doc.public_url} target="_blank" rel="noreferrer" className="block text-primary text-body-sm font-semibold hover:underline pt-1" dir="ltr">
            {doc.public_url}
          </a>
        )}
      </div>
    </div>
  );
}

function DetailRow({ label, value, mono, badge }: { label: string; value: string; mono?: boolean; badge?: string }) {
  return (
    <div className="flex items-center justify-between text-body-sm">
      <span className="text-on-surface-variant">{label}</span>
      {badge ? (
        <span className={`px-2 py-1 rounded text-[11px] font-bold ${badge}`}>{value}</span>
      ) : (
        <span className={mono ? "font-data-mono text-on-surface" : "text-on-surface"} dir={mono ? "ltr" : undefined}>
          {value}
        </span>
      )}
    </div>
  );
}

// ── EGS Codes registry (read-only) ───────────────────────────────────────────

function EgsCodesCard() {
  const { data: codes, isLoading, isError } = useQuery({
    queryKey: ["eta-egs-codes"],
    queryFn: async () => {
      const res = await apiClient.get<EgsCode[]>("/eta/egs-codes");
      return res.data;
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <Tags className="w-4 h-4" />
        </div>
        <div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">سجل أكواد EGS/GS1</h2>
          <p className="text-body-sm text-on-surface-variant">ربط الأصناف بأكواد المصلحة المطلوبة قبل أي إرسال.</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل سجل الأكواد.
        </div>
      ) : !codes || codes.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-on-surface-variant gap-2">
          <Tags className="w-7 h-7 text-outline-variant" />
          <p className="text-body-sm">لا توجد أكواد مسجّلة بعد.</p>
        </div>
      ) : (
        <div className="overflow-x-auto max-h-96 overflow-y-auto">
          <table className="w-full text-right">
            <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant sticky top-0">
              <tr>
                <th className="px-4 py-3">الاسم</th>
                <th className="px-4 py-3">النوع</th>
                <th className="px-4 py-3">الكود</th>
                <th className="px-4 py-3">الحالة</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/30 text-body-sm">
              {codes.map((c) => (
                <tr key={c.id} className="hover:bg-surface-container-lowest transition-colors">
                  <td className="px-4 py-3">{c.name_ar ?? c.name_en ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 rounded text-[11px] font-bold bg-primary-container/10 text-primary">{c.code_type}</span>
                  </td>
                  <td className="px-4 py-3 font-data-mono" dir="ltr">{c.code_value}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-[11px] font-bold ${c.is_active ? "bg-success-bg text-success" : "bg-surface-container text-on-surface-variant"}`}>
                      {c.is_active ? "نشط" : "غير نشط"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
