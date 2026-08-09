"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient } from "@/lib/api-client";
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
            {(mutation.error as AxiosError<{ detail?: string }>)?.response?.data?.detail || "تعذر إنشاء طلب التوظيف."}
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
      setError(err.response?.data?.detail || "تعذر إرفاق المرشح.");
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
      setError(err.response?.data?.detail || "تعذر استيراد الملف.");
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
