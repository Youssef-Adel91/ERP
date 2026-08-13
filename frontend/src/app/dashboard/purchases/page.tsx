"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { ShoppingCart, Plus, Trash2, Loader2, AlertCircle, X, CheckCircle2, GitMerge } from "lucide-react";

/**
 * Cut over from app.plugins.purchases ("/purchases/invoices") to
 * app.modules.purchasing ("/purchasing/bills"). The new VendorBill is a
 * stricter three-way-match document: lines reference an optional
 * po_line_id/grn_line_id (not an item_id — there's no PO/GRN creation UI
 * yet, so bills raised here are unlinked and match trivially at 0 variance),
 * and posting requires running the match step first.
 */

type VendorBillStatus = "DRAFT" | "APPROVED" | "POSTED" | "CANCELLED";
type MatchState = "UNMATCHED" | "MATCHED" | "VARIANCE_WITHIN_TOLERANCE" | "VARIANCE_BLOCKED";

interface Contact { id: string; name: string; contact_type: "customer" | "supplier"; }

interface VendorBill {
  id: string;
  bill_number: string;
  supplier_id: string;
  bill_date: string;
  due_date: string;
  status: VendorBillStatus;
  match_state: MatchState;
  total_amount: string | number;
}

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const statusLabel: Record<VendorBillStatus, string> = { DRAFT: "مسودة", APPROVED: "معتمدة", POSTED: "مرحّلة", CANCELLED: "ملغاة" };
const statusTone: Record<VendorBillStatus, string> = {
  DRAFT: "bg-primary-container/10 text-primary",
  APPROVED: "bg-warning-bg text-warning",
  POSTED: "bg-success-bg text-success",
  CANCELLED: "bg-error-container text-on-error-container",
};
const matchLabel: Record<MatchState, string> = {
  UNMATCHED: "غير مطابقة",
  MATCHED: "مطابقة",
  VARIANCE_WITHIN_TOLERANCE: "فرق ضمن الحد المسموح",
  VARIANCE_BLOCKED: "فرق محظور",
};
const matchTone: Record<MatchState, string> = {
  UNMATCHED: "bg-surface-container text-on-surface-variant",
  MATCHED: "bg-success-bg text-success",
  VARIANCE_WITHIN_TOLERANCE: "bg-warning-bg text-warning",
  VARIANCE_BLOCKED: "bg-error-container text-on-error-container",
};

export default function PurchasesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const { data: bills, isLoading, isError } = useQuery({
    queryKey: ["purchasing-bills"],
    queryFn: async () => {
      const res = await apiClient.get<VendorBill[]>("/purchasing/bills");
      return res.data;
    },
  });

  const { data: contacts } = useQuery({
    queryKey: ["contacts", "for-purchases"],
    queryFn: async () => {
      const res = await apiClient.get<{ items: Contact[] }>("/contacts", { params: { limit: 200 } });
      return res.data.items;
    },
  });
  const suppliers = (contacts ?? []).filter((c) => c.contact_type === "supplier");
  const contactsById = new Map((contacts ?? []).map((c) => [c.id, c]));

  const matchMutation = useMutation({
    mutationFn: async (id: string) => { await apiClient.post(`/purchasing/bills/${id}/match`); },
    onMutate: (id) => { setActionError(""); setBusyId(id); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["purchasing-bills"] }),
    onError: (err: AxiosError<{ detail?: string }>) => setActionError(pickDetail(err, "تعذرت المطابقة الثلاثية.")),
    onSettled: () => setBusyId(null),
  });

  const postMutation = useMutation({
    mutationFn: async (id: string) => { await apiClient.post(`/purchasing/bills/${id}/post`); },
    onMutate: (id) => { setActionError(""); setBusyId(id); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["purchasing-bills"] }),
    onError: (err: AxiosError<{ detail?: string }>) => setActionError(pickDetail(err, "تعذر ترحيل الفاتورة (تأكد من إجراء المطابقة أولاً).")),
    onSettled: () => setBusyId(null),
  });

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">المشتريات</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">فواتير الموردين — تتطلب مطابقة ثلاثية قبل الترحيل للحسابات.</p>
        </div>
        <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
          <Plus className="w-4 h-4" /> فاتورة مورد جديدة
        </button>
      </div>

      {actionError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {actionError}
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error"><AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل فواتير الموردين.</div>
        ) : !bills || bills.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <ShoppingCart className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد فواتير موردين بعد.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">رقم الفاتورة</th>
                  <th className="px-6 py-4">المورد</th>
                  <th className="px-6 py-4">التاريخ</th>
                  <th className="px-6 py-4">حالة الفاتورة</th>
                  <th className="px-6 py-4">حالة المطابقة</th>
                  <th className="px-6 py-4">الإجمالي</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {bills.map((bill) => {
                  const busy = busyId === bill.id;
                  return (
                    <tr key={bill.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{bill.bill_number}</td>
                      <td className="px-6 py-4 font-medium">{contactsById.get(bill.supplier_id)?.name ?? "—"}</td>
                      <td className="px-6 py-4 text-outline font-data-mono" dir="ltr">{new Date(bill.bill_date).toLocaleDateString("en-GB")}</td>
                      <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[bill.status]}`}>{statusLabel[bill.status]}</span></td>
                      <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${matchTone[bill.match_state]}`}>{matchLabel[bill.match_state]}</span></td>
                      <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">{egp(bill.total_amount)}</td>
                      <td className="px-6 py-4">
                        {bill.status === "DRAFT" && bill.match_state !== "MATCHED" && (
                          <button onClick={() => matchMutation.mutate(bill.id)} disabled={busy} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary-container/10 text-primary font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50">
                            {busy && matchMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <GitMerge className="w-3.5 h-3.5" />} مطابقة
                          </button>
                        )}
                        {bill.status === "DRAFT" && bill.match_state === "MATCHED" && (
                          <button onClick={() => postMutation.mutate(bill.id)} disabled={busy} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success-bg text-success font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50">
                            {busy && postMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />} ترحيل
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <CreateBillModal
          suppliers={suppliers}
          onClose={() => setModalOpen(false)}
          onCreated={() => { setModalOpen(false); queryClient.invalidateQueries({ queryKey: ["purchasing-bills"] }); }}
        />
      )}
    </div>
  );
}

const lineSchema = z.object({
  qty_billed: z.coerce.number().gt(0, "الكمية أكبر من صفر"),
  unit_price: z.coerce.number().min(0, "السعر لازم يكون رقم موجب"),
});
const schema = z.object({
  supplier_id: z.string().min(1, "اختر المورد"),
  bill_number: z.string().min(1, "رقم الفاتورة مطلوب"),
  lines: z.array(lineSchema).min(1),
});
type FormOut = z.output<typeof schema>;
type FormIn = z.input<typeof schema>;

function CreateBillModal({ suppliers, onClose, onCreated }: { suppliers: Contact[]; onClose: () => void; onCreated: () => void }) {
  const [errorMsg, setErrorMsg] = useState("");
  const { register, control, handleSubmit, formState: { errors } } = useForm<FormIn, any, FormOut>({
    resolver: zodResolver(schema),
    defaultValues: { supplier_id: "", bill_number: "", lines: [{ qty_billed: 1, unit_price: 0 }] },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "lines" });

  const mutation = useMutation({
    mutationFn: async (data: FormOut) => {
      await apiClient.post("/purchasing/bills", {
        supplier_id: data.supplier_id,
        bill_number: data.bill_number,
        lines: data.lines.map((l) => ({ qty_billed: l.qty_billed, unit_price: l.unit_price })),
      });
    },
    onSuccess: onCreated,
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إنشاء فاتورة المورد.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">فاتورة مورد جديدة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        {suppliers.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">أضف مورد واحد على الأقل (من جهات الاتصال) قبل تسجيل فاتورة.</p>
        ) : (
          <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">المورد</label>
                <select {...register("supplier_id")} className="input-field">
                  <option value="">اختر المورد</option>
                  {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                {errors.supplier_id && <p className="text-body-sm text-error">{errors.supplier_id.message}</p>}
              </div>
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">رقم الفاتورة</label>
                <input {...register("bill_number")} dir="ltr" className="input-field font-mono" />
                {errors.bill_number && <p className="text-body-sm text-error">{errors.bill_number.message}</p>}
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-body-sm font-semibold text-on-surface-variant">البنود (بدون ربط بأمر شراء — تُطابق تلقائيًا بفرق صفري)</label>
              {fields.map((field, idx) => (
                <div key={field.id} className="flex gap-2 items-start">
                  <input type="number" step="1" placeholder="الكمية" dir="ltr" {...register(`lines.${idx}.qty_billed` as const)} className="input-field w-28 font-mono" />
                  <input type="number" step="0.01" placeholder="السعر" dir="ltr" {...register(`lines.${idx}.unit_price` as const)} className="input-field w-28 font-mono" />
                  <button type="button" onClick={() => remove(idx)} className="p-2.5 text-error hover:bg-error-container/20 rounded-lg transition-colors shrink-0"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
              {errors.lines?.message && <p className="text-body-sm text-error">{errors.lines.message}</p>}
              <button type="button" onClick={() => append({ qty_billed: 1, unit_price: 0 })} className="flex items-center gap-1 text-primary font-semibold text-body-sm hover:underline">
                <Plus className="w-4 h-4" /> إضافة بند
              </button>
            </div>

            <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
              {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الفاتورة
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
