"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  UserSearch,
  Plus,
  Loader2,
  AlertCircle,
  X,
  Upload,
  Users,
  CheckCircle2,
  Ban,
  Contact2,
  CalendarClock,
  FileDown,
  Pencil,
} from "lucide-react";

/**
 * Recruitment plugin dashboard — Job Orders (foreign employer staffing
 * demand), candidate matching, and bulk Excel import. Candidates themselves
 * are Cases (case_type "candidate_deployment") — created/edited via the
 * generic Cases screen (/dashboard/cases) and its detail page, not
 * duplicated here. This page is the recruitment-specific layer on top:
 * matching candidates to job orders and importing them in bulk.
 */

interface Contact { id: string; name: string; contact_type: "customer" | "supplier"; }

interface JobOrder {
  id: string;
  order_reference: string;
  sponsor_id: string;
  required_profession: string;
  target_country: string;
  target_count: number;
  fulfilled_count: number;
  status: "OPEN" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED" | "EXPIRED";
  notes: string | null;
}

interface MatchedCandidate {
  case_id: string;
  title: string | null;
  stage: string;
  profession: string | null;
  nationality: string | null;
  passport_number: string | null;
}

const statusMeta: Record<JobOrder["status"], string> = {
  OPEN: "bg-primary-container/10 text-primary",
  PARTIALLY_FILLED: "bg-warning-bg text-warning",
  FILLED: "bg-success-bg text-success",
  CANCELLED: "bg-error-container text-on-error-container",
  EXPIRED: "bg-surface-container text-on-surface-variant",
};
const statusLabel: Record<JobOrder["status"], string> = {
  OPEN: "مفتوح",
  PARTIALLY_FILLED: "مكتمل جزئيًا",
  FILLED: "مكتمل",
  CANCELLED: "ملغى",
  EXPIRED: "منتهي",
};

export default function RecruitmentPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<JobOrder | null>(null);
  const [attachedOrder, setAttachedOrder] = useState<JobOrder | null>(null);
  const [importOrderId, setImportOrderId] = useState<string | null>(null);

  const { data: jobOrders, isLoading, isError } = useQuery({
    queryKey: ["recruitment-job-orders"],
    queryFn: async () => {
      const res = await apiClient.get<JobOrder[]>("/recruitment/job-orders");
      return res.data;
    },
  });

  const queryClient = useQueryClient();
  const cancelMutation = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/recruitment/job-orders/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recruitment-job-orders"] }),
  });

  return (
    <div className="space-y-gutter">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الاستقدام والتوظيف الخارجي</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            طلبات التوظيف من أصحاب العمل بالخارج، ومطابقة المرشحين تلقائيًا.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setImportOrderId("")}
            className="flex items-center gap-2 h-10 px-4 rounded-lg border border-outline-variant text-on-surface-variant font-semibold text-body-sm hover:bg-surface-container transition-colors"
          >
            <Upload className="w-4 h-4" /> استيراد جماعي
          </button>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity"
          >
            <Plus className="w-4 h-4" /> طلب توظيف جديد
          </button>
        </div>
      </div>

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل طلبات التوظيف.
          </div>
        ) : !jobOrders || jobOrders.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <UserSearch className="w-7 h-7 text-outline-variant" />
            <p className="text-body-sm">لا توجد طلبات توظيف بعد.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">المرجع</th>
                  <th className="px-6 py-4">المهنة المطلوبة</th>
                  <th className="px-6 py-4">الدولة</th>
                  <th className="px-6 py-4">الإنجاز</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {jobOrders.map((o) => (
                  <tr key={o.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-medium font-data-mono" dir="ltr">{o.order_reference}</td>
                    <td className="px-6 py-4">{o.required_profession}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{o.target_country}</td>
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{o.fulfilled_count} / {o.target_count}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-[11px] font-bold ${statusMeta[o.status]}`}>
                        {statusLabel[o.status]}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-4">
                        <button
                          onClick={() => setSelectedOrder(o)}
                          className="flex items-center gap-1.5 text-primary font-semibold text-body-sm hover:underline"
                        >
                          <Users className="w-3.5 h-3.5" /> المرشحون المطابقون
                        </button>
                        {o.fulfilled_count > 0 && (
                          <button
                            onClick={() => setAttachedOrder(o)}
                            className="flex items-center gap-1.5 text-on-surface-variant font-semibold text-body-sm hover:text-on-surface"
                          >
                            <Contact2 className="w-3.5 h-3.5" /> المرشحون المرفقون
                          </button>
                        )}
                        {(o.status === "OPEN" || o.status === "PARTIALLY_FILLED") && (
                          <button
                            onClick={() => {
                              if (confirm(`هل أنت متأكد من إلغاء طلب التوظيف ${o.order_reference}؟`)) {
                                cancelMutation.mutate(o.id);
                              }
                            }}
                            disabled={cancelMutation.isPending}
                            className="flex items-center gap-1.5 text-error font-semibold text-body-sm hover:underline disabled:opacity-50"
                          >
                            <Ban className="w-3.5 h-3.5" /> إلغاء
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && <CreateJobOrderModal onClose={() => setModalOpen(false)} />}
      {selectedOrder && (
        <MatchingPanel jobOrder={selectedOrder} onClose={() => setSelectedOrder(null)} />
      )}
      {attachedOrder && (
        <AttachedCandidatesPanel jobOrder={attachedOrder} onClose={() => setAttachedOrder(null)} />
      )}
      {importOrderId !== null && (
        <BulkImportModal
          jobOrders={jobOrders ?? []}
          onClose={() => setImportOrderId(null)}
        />
      )}
    </div>
  );
}

// ── Create Job Order ──────────────────────────────────────────────────────────

const jobOrderSchema = z.object({
  order_reference: z.string().min(1, "المرجع مطلوب"),
  sponsor_id: z.string().min(1, "صاحب العمل مطلوب"),
  required_profession: z.string().min(1, "المهنة مطلوبة"),
  target_country: z.string().min(1, "الدولة مطلوبة"),
  target_count: z.string().min(1, "العدد مطلوب"),
  notes: z.string().optional(),
});
type JobOrderForm = z.infer<typeof jobOrderSchema>;

function CreateJobOrderModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors } } = useForm<JobOrderForm>({
    resolver: zodResolver(jobOrderSchema),
    defaultValues: { order_reference: "", sponsor_id: "", required_profession: "", target_country: "", target_count: "1", notes: "" },
  });

  const { data: sponsors } = useQuery({
    queryKey: ["recruitment-sponsors"],
    queryFn: async () => {
      const res = await apiClient.get<{ items: Contact[] }>("/contacts", { params: { limit: 200 } });
      return res.data.items;
    },
  });

  const mutation = useMutation({
    mutationFn: async (data: JobOrderForm) => {
      await apiClient.post("/recruitment/job-orders", { ...data, target_count: Number(data.target_count) });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruitment-job-orders"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-5">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">طلب توظيف جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {mutation.isError && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {pickDetail(mutation.error, "تعذر إنشاء طلب التوظيف.")}
          </div>
        )}
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">المرجع</label>
            <input {...register("order_reference")} dir="ltr" className="input-field font-mono" />
            {errors.order_reference && <p className="text-body-sm text-error">{errors.order_reference.message}</p>}
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">صاحب العمل / الكفيل</label>
            <select {...register("sponsor_id")} className="input-field">
              <option value="">اختر...</option>
              {sponsors?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {errors.sponsor_id && <p className="text-body-sm text-error">{errors.sponsor_id.message}</p>}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">المهنة المطلوبة</label>
              <input {...register("required_profession")} className="input-field" />
              {errors.required_profession && <p className="text-body-sm text-error">{errors.required_profession.message}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الدولة</label>
              <input {...register("target_country")} className="input-field" />
              {errors.target_country && <p className="text-body-sm text-error">{errors.target_country.message}</p>}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">عدد المطلوبين</label>
            <input type="number" {...register("target_count")} dir="ltr" className="input-field font-mono" min={1} />
            {errors.target_count && <p className="text-body-sm text-error">{errors.target_count.message}</p>}
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">ملاحظات</label>
            <textarea {...register("notes")} rows={2} className="input-field" />
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} إنشاء الطلب
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Matching panel ────────────────────────────────────────────────────────────

function MatchingPanel({ jobOrder, onClose }: { jobOrder: JobOrder; onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["job-order-matches", jobOrder.id],
    queryFn: async () => {
      const res = await apiClient.get<{ matched_count: number; candidates: MatchedCandidate[] }>(
        `/recruitment/job-orders/${jobOrder.id}/candidates/match`
      );
      return res.data;
    },
  });

  const attachMutation = useMutation({
    mutationFn: async (caseId: string) => {
      await apiClient.post(`/recruitment/job-orders/${jobOrder.id}/candidates`, { case_id: caseId });
    },
    onSuccess: () => {
      setError("");
      queryClient.invalidateQueries({ queryKey: ["job-order-matches", jobOrder.id] });
      queryClient.invalidateQueries({ queryKey: ["recruitment-job-orders"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setError(pickDetail(err, "تعذر إرفاق المرشح."));
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div
        className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="font-headline-sm text-headline-sm text-on-surface">مرشحون مطابقون</h3>
            <p className="text-body-sm text-on-surface-variant font-data-mono" dir="ltr">{jobOrder.order_reference} — {jobOrder.required_profession}</p>
          </div>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-3 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري البحث عن مرشحين...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل المرشحين.
          </div>
        ) : !data || data.candidates.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant py-6 text-center">
            لا يوجد مرشحون غير مرتبطين مطابقون للمهنة "{jobOrder.required_profession}" حاليًا.
          </p>
        ) : (
          <div className="space-y-2">
            {data.candidates.map((c) => (
              <div key={c.case_id} className="flex items-center justify-between p-3 rounded-lg border border-outline-variant/40">
                <div className="cursor-pointer" onClick={() => router.push(`/dashboard/cases/${c.case_id}`)}>
                  <p className="text-body-md font-medium text-on-surface hover:underline">{c.title ?? "بدون عنوان"}</p>
                  <p className="text-body-sm text-on-surface-variant">
                    {c.profession ?? "—"} · {c.nationality ?? "—"} ·{" "}
                    <span className="font-data-mono" dir="ltr">{c.passport_number ?? "—"}</span>
                  </p>
                </div>
                <button
                  onClick={() => attachMutation.mutate(c.case_id)}
                  disabled={attachMutation.isPending}
                  className="h-9 px-3 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70 shrink-0"
                >
                  إرفاق
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Bulk Excel import ──────────────────────────────────────────────────────────

interface ImportRowResult { row: number; status: string; case_id: string | null; error: string | null; }
interface ImportResult { summary: { total: number; created: number; skipped: number; errors: number }; rows: ImportRowResult[]; }

function BulkImportModal({ jobOrders, onClose }: { jobOrders: JobOrder[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [jobOrderId, setJobOrderId] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await apiClient.post<ImportResult>("/recruitment/candidates/import", form, {
        params: jobOrderId ? { job_order_id: jobOrderId } : {},
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data;
    },
    onSuccess: (data) => {
      setError("");
      setResult(data);
      queryClient.invalidateQueries({ queryKey: ["recruitment-job-orders"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setError(pickDetail(err, "تعذر استيراد الملف."));
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-5">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">استيراد جماعي من Excel</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">إرفاق بطلب توظيف (اختياري)</label>
            <select value={jobOrderId} onChange={(e) => setJobOrderId(e.target.value)} className="input-field">
              <option value="">بدون إرفاق</option>
              {jobOrders.map((o) => <option key={o.id} value={o.id}>{o.order_reference} — {o.required_profession}</option>)}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">ملف Excel (.xlsx)</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) mutation.mutate(file);
              }}
              className="input-field"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </div>
          )}
          {mutation.isPending && (
            <div className="flex items-center justify-center py-6 text-on-surface-variant gap-2">
              <Loader2 className="w-5 h-5 animate-spin" /> جاري الاستيراد...
            </div>
          )}
          {result && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg text-body-sm font-medium border border-success">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                تم استيراد {result.summary.created} من أصل {result.summary.total} — تخطي {result.summary.skipped}، أخطاء {result.summary.errors}
              </div>
              <div className="max-h-48 overflow-y-auto divide-y divide-outline-variant/30 text-body-sm">
                {result.rows.map((r) => (
                  <div key={r.row} className="flex items-center justify-between py-1.5">
                    <span className="text-on-surface-variant">صف {r.row}</span>
                    <span className={r.status === "created" ? "text-success" : "text-error"}>
                      {r.error ?? r.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Attached candidates panel ───────────────────────────────────────────────

interface AttachedCandidate {
  case_id: string;
  link_id: string;
  full_name: string;
  profession: string | null;
  stage: string;
  has_candidate_profile: boolean;
}

function AttachedCandidatesPanel({ jobOrder, onClose }: { jobOrder: JobOrder; onClose: () => void }) {
  const [profileCaseId, setProfileCaseId] = useState<string | null>(null);
  const [interviewsCaseId, setInterviewsCaseId] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState("");
  const [pdfDownloadingId, setPdfDownloadingId] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["job-order-attached-candidates", jobOrder.id],
    queryFn: async () => {
      const res = await apiClient.get<{ job_order_id: string; candidates: AttachedCandidate[] }>(
        `/recruitment/job-orders/${jobOrder.id}/candidates`
      );
      return res.data.candidates;
    },
  });

  const offerLetterMutation = useMutation({
    mutationFn: async (candidate: AttachedCandidate) => {
      const res = await apiClient.get(
        `/recruitment/job-orders/${jobOrder.id}/candidates/${candidate.case_id}/offer-letter`,
        { responseType: "blob" }
      );
      return { candidate, blob: res.data as Blob };
    },
    onMutate: (candidate) => { setPdfError(""); setPdfDownloadingId(candidate.case_id); },
    onSuccess: ({ candidate, blob }) => {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `offer_letter_${candidate.case_id.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
    onError: (err: AxiosError<{ detail?: string }>) => setPdfError(pickDetail(err, "تعذر تحميل خطاب العرض.")),
    onSettled: () => setPdfDownloadingId(null),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div
        className="w-full max-w-2xl bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="font-headline-sm text-headline-sm text-on-surface">المرشحون المرفقون</h3>
            <p className="text-body-sm text-on-surface-variant font-data-mono" dir="ltr">{jobOrder.order_reference} — {jobOrder.required_profession}</p>
          </div>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {pdfError && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-3 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {pdfError}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل المرشحين المرفقين.
          </div>
        ) : !data || data.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant py-6 text-center">لا يوجد مرشحون مرفقون بهذا الطلب بعد.</p>
        ) : (
          <div className="space-y-2">
            {data.map((c) => (
              <div key={c.case_id} className="p-3 rounded-lg border border-outline-variant/40 space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-body-md font-medium text-on-surface">{c.full_name}</p>
                    <p className="text-body-sm text-on-surface-variant">{c.profession ?? "—"} · {c.stage}</p>
                  </div>
                  {!c.has_candidate_profile && (
                    <span className="text-[11px] px-2 py-1 rounded bg-warning-bg text-warning font-bold">بدون ملف منظم</span>
                  )}
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                  <button
                    onClick={() => setProfileCaseId(c.case_id)}
                    className="flex items-center gap-1.5 text-primary font-semibold text-body-sm hover:underline"
                  >
                    <Pencil className="w-3.5 h-3.5" /> الملف الشخصي
                  </button>
                  <button
                    onClick={() => setInterviewsCaseId(c.case_id)}
                    className="flex items-center gap-1.5 text-on-surface-variant font-semibold text-body-sm hover:text-on-surface"
                  >
                    <CalendarClock className="w-3.5 h-3.5" /> المقابلات
                  </button>
                  <button
                    onClick={() => offerLetterMutation.mutate(c)}
                    disabled={pdfDownloadingId === c.case_id}
                    className="flex items-center gap-1.5 text-on-surface-variant font-semibold text-body-sm hover:text-on-surface disabled:opacity-50"
                  >
                    {pdfDownloadingId === c.case_id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <FileDown className="w-3.5 h-3.5" />
                    )}{" "}
                    خطاب عرض
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {profileCaseId && (
        <CandidateProfileModal caseId={profileCaseId} onClose={() => setProfileCaseId(null)} />
      )}
      {interviewsCaseId && (
        <InterviewsModal caseId={interviewsCaseId} jobOrderId={jobOrder.id} onClose={() => setInterviewsCaseId(null)} />
      )}
    </div>
  );
}

// ── Candidate structured profile ────────────────────────────────────────────

interface CandidateProfile {
  id: string;
  case_id: string;
  full_name: string;
  full_name_ar: string | null;
  passport_number: string | null;
  passport_expiry: string | null;
  date_of_birth: string | null;
  nationality: string | null;
  gender: string | null;
  profession: string | null;
  phone: string | null;
  expected_salary: string | null;
  availability_status: string;
  notes: string | null;
}

const candidateProfileSchema = z.object({
  full_name: z.string().min(1, "الاسم مطلوب"),
  full_name_ar: z.string().optional(),
  passport_number: z.string().optional(),
  passport_expiry: z.string().optional(),
  date_of_birth: z.string().optional(),
  nationality: z.string().optional(),
  gender: z.string().optional(),
  profession: z.string().optional(),
  phone: z.string().optional(),
  expected_salary: z.string().optional(),
  availability_status: z.string().default("AVAILABLE"),
  notes: z.string().optional(),
});
type CandidateProfileForm = z.infer<typeof candidateProfileSchema>;

function CandidateProfileModal({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const queryClient = useQueryClient();

  const { data: existing, isLoading } = useQuery({
    queryKey: ["candidate-profile", caseId],
    queryFn: async () => {
      try {
        const res = await apiClient.get<CandidateProfile>(`/recruitment/cases/${caseId}/candidate-profile`);
        return res.data;
      } catch (err) {
        if ((err as AxiosError).response?.status === 404) return null;
        throw err;
      }
    },
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<CandidateProfileForm>({
    resolver: zodResolver(candidateProfileSchema),
    defaultValues: { full_name: "", availability_status: "AVAILABLE" },
    values: existing
      ? {
          full_name: existing.full_name,
          full_name_ar: existing.full_name_ar ?? "",
          passport_number: existing.passport_number ?? "",
          passport_expiry: existing.passport_expiry ?? "",
          date_of_birth: existing.date_of_birth ?? "",
          nationality: existing.nationality ?? "",
          gender: existing.gender ?? "",
          profession: existing.profession ?? "",
          phone: existing.phone ?? "",
          expected_salary: existing.expected_salary ?? "",
          availability_status: existing.availability_status,
          notes: existing.notes ?? "",
        }
      : undefined,
  });

  const mutation = useMutation({
    mutationFn: async (data: CandidateProfileForm) => {
      const payload = {
        ...data,
        passport_expiry: data.passport_expiry || null,
        date_of_birth: data.date_of_birth || null,
        expected_salary: data.expected_salary || null,
      };
      await apiClient.put(`/recruitment/cases/${caseId}/candidate-profile`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["candidate-profile", caseId] });
      queryClient.invalidateQueries({ queryKey: ["job-order-attached-candidates"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-5">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">الملف الشخصي للمرشح</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : (
          <>
            {mutation.isError && (
              <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {pickDetail(mutation.error, "تعذر حفظ الملف الشخصي.")}
              </div>
            )}
            <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">الاسم الكامل</label>
                  <input {...register("full_name")} className="input-field" />
                  {errors.full_name && <p className="text-body-sm text-error">{errors.full_name.message}</p>}
                </div>
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">الاسم بالعربية</label>
                  <input {...register("full_name_ar")} className="input-field" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">رقم جواز السفر</label>
                  <input {...register("passport_number")} dir="ltr" className="input-field font-mono" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">تاريخ انتهاء الجواز</label>
                  <input type="date" {...register("passport_expiry")} dir="ltr" className="input-field font-mono" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">تاريخ الميلاد</label>
                  <input type="date" {...register("date_of_birth")} dir="ltr" className="input-field font-mono" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">الجنسية</label>
                  <input {...register("nationality")} className="input-field" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">المهنة</label>
                  <input {...register("profession")} className="input-field" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">الراتب المتوقع</label>
                  <input {...register("expected_salary")} dir="ltr" className="input-field font-mono" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">رقم الهاتف</label>
                  <input {...register("phone")} dir="ltr" className="input-field font-mono" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-body-sm font-semibold text-on-surface-variant">حالة التوفر</label>
                  <select {...register("availability_status")} className="input-field">
                    <option value="AVAILABLE">متاح</option>
                    <option value="MATCHED">تمت المطابقة</option>
                    <option value="DEPLOYED">تم النشر</option>
                    <option value="UNAVAILABLE">غير متاح</option>
                  </select>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">ملاحظات</label>
                <textarea {...register("notes")} rows={2} className="input-field" />
              </div>
              <button
                type="submit"
                disabled={mutation.isPending}
                className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
              >
                {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الملف الشخصي
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// ── Interview scheduling ────────────────────────────────────────────────────

interface Interview {
  id: string;
  case_id: string;
  job_order_id: string | null;
  scheduled_at: string;
  interviewer_name: string | null;
  location: string | null;
  result: string;
  notes: string | null;
}

const interviewResultLabel: Record<string, string> = {
  PENDING: "قيد الانتظار",
  PASSED: "ناجحة",
  FAILED: "غير ناجحة",
  RESCHEDULED: "أُعيدت جدولتها",
  NO_SHOW: "لم يحضر",
};
const interviewResultTone: Record<string, string> = {
  PENDING: "bg-surface-container text-on-surface-variant",
  PASSED: "bg-success-bg text-success",
  FAILED: "bg-error-container text-on-error-container",
  RESCHEDULED: "bg-warning-bg text-warning",
  NO_SHOW: "bg-error-container text-on-error-container",
};

const interviewSchema = z.object({
  scheduled_at: z.string().min(1, "الموعد مطلوب"),
  interviewer_name: z.string().optional(),
  location: z.string().optional(),
  notes: z.string().optional(),
});
type InterviewForm = z.infer<typeof interviewSchema>;

function InterviewsModal({ caseId, jobOrderId, onClose }: { caseId: string; jobOrderId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { data: interviews, isLoading, isError } = useQuery({
    queryKey: ["candidate-interviews", caseId],
    queryFn: async () => {
      const res = await apiClient.get<Interview[]>(`/recruitment/cases/${caseId}/interviews`);
      return res.data;
    },
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<InterviewForm>({
    resolver: zodResolver(interviewSchema),
    defaultValues: { scheduled_at: "", interviewer_name: "", location: "", notes: "" },
  });

  const scheduleMutation = useMutation({
    mutationFn: async (data: InterviewForm) => {
      await apiClient.post(`/recruitment/cases/${caseId}/interviews`, {
        ...data,
        job_order_id: jobOrderId,
        scheduled_at: new Date(data.scheduled_at).toISOString(),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["candidate-interviews", caseId] });
      setShowForm(false);
      reset();
    },
  });

  const resultMutation = useMutation({
    mutationFn: async ({ id, result }: { id: string; result: string }) => {
      await apiClient.post(`/recruitment/cases/${caseId}/interviews/${id}/result`, { result });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["candidate-interviews", caseId] }),
  });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-5">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">مقابلات المرشح</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 h-9 px-3 mb-4 rounded-lg border border-outline-variant text-on-surface font-semibold text-body-sm hover:bg-surface-container transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> جدولة مقابلة جديدة
        </button>

        {showForm && (
          <form onSubmit={handleSubmit((d) => scheduleMutation.mutate(d))} className="space-y-3 mb-5 p-3 rounded-lg border border-outline-variant/40">
            {scheduleMutation.isError && (
              <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {pickDetail(scheduleMutation.error, "تعذر جدولة المقابلة.")}
              </div>
            )}
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الموعد</label>
              <input type="datetime-local" {...register("scheduled_at")} dir="ltr" className="input-field font-mono" />
              {errors.scheduled_at && <p className="text-body-sm text-error">{errors.scheduled_at.message}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">القائم بالمقابلة</label>
              <input {...register("interviewer_name")} className="input-field" />
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">المكان / رابط المقابلة</label>
              <input {...register("location")} className="input-field" />
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">ملاحظات</label>
              <textarea {...register("notes")} rows={2} className="input-field" />
            </div>
            <button
              type="submit"
              disabled={scheduleMutation.isPending}
              className="w-full flex items-center justify-center gap-2 h-10 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70"
            >
              {scheduleMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} جدولة
            </button>
          </form>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل المقابلات.
          </div>
        ) : !interviews || interviews.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant py-6 text-center">لا توجد مقابلات مجدولة بعد.</p>
        ) : (
          <div className="space-y-2">
            {interviews.map((iv) => (
              <div key={iv.id} className="p-3 rounded-lg border border-outline-variant/40 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-body-sm font-data-mono" dir="ltr">{new Date(iv.scheduled_at).toLocaleString("ar-EG")}</p>
                  <span className={`px-2 py-1 rounded text-[11px] font-bold ${interviewResultTone[iv.result] ?? ""}`}>
                    {interviewResultLabel[iv.result] ?? iv.result}
                  </span>
                </div>
                <p className="text-body-sm text-on-surface-variant">
                  {iv.interviewer_name ?? "—"} {iv.location ? `· ${iv.location}` : ""}
                </p>
                {iv.result === "PENDING" && (
                  <div className="flex items-center gap-3 pt-1">
                    <button
                      onClick={() => resultMutation.mutate({ id: iv.id, result: "PASSED" })}
                      className="text-success font-semibold text-body-sm hover:underline"
                    >
                      ناجحة
                    </button>
                    <button
                      onClick={() => resultMutation.mutate({ id: iv.id, result: "FAILED" })}
                      className="text-error font-semibold text-body-sm hover:underline"
                    >
                      غير ناجحة
                    </button>
                    <button
                      onClick={() => resultMutation.mutate({ id: iv.id, result: "NO_SHOW" })}
                      className="text-on-surface-variant font-semibold text-body-sm hover:underline"
                    >
                      لم يحضر
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
