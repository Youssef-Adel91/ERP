"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import {
  Landmark,
  Plus,
  Loader2,
  AlertCircle,
  X,
  ArrowDownCircle,
  CheckCircle2,
  XCircle,
} from "lucide-react";

type ChequeType = "incoming" | "outgoing";
type ChequeStatus = "pending" | "deposited" | "cleared" | "bounced" | "cancelled";

interface Cheque {
  id: string;
  cheque_number: string;
  amount: string | number;
  issue_date: string;
  due_date: string;
  bank_name: string;
  cheque_type: ChequeType;
  status: ChequeStatus;
  contact_id: string;
}

interface Contact {
  id: string;
  name: string;
}

const egp = (value: string | number) => `${Number(value).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const typeLabel: Record<ChequeType, string> = { incoming: "وارد (من عميل)", outgoing: "صادر (لمورد)" };
const statusLabel: Record<ChequeStatus, string> = {
  pending: "بالانتظار",
  deposited: "تم الإيداع",
  cleared: "تم التحصيل",
  bounced: "مرتجع",
  cancelled: "ملغي",
};
const statusTone: Record<ChequeStatus, string> = {
  pending: "bg-primary-container/10 text-primary",
  deposited: "bg-tertiary-container/10 text-tertiary",
  cleared: "bg-secondary-container/30 text-secondary",
  bounced: "bg-error-container/40 text-error",
  cancelled: "bg-surface-container text-on-surface-variant",
};

const createChequeSchema = z.object({
  cheque_number: z.string().min(1, "رقم الشيك مطلوب"),
  amount: z.coerce.number().gt(0, "المبلغ لازم يكون أكبر من صفر"),
  issue_date: z.string().min(1, "تاريخ الإصدار مطلوب"),
  due_date: z.string().min(1, "تاريخ الاستحقاق مطلوب"),
  bank_name: z.string().min(1, "اسم البنك مطلوب"),
  cheque_type: z.enum(["incoming", "outgoing"]),
  contact_id: z.string().min(1, "اختر جهة الاتصال"),
});
type CreateChequeForm = z.output<typeof createChequeSchema>;
type CreateChequeFormInput = z.input<typeof createChequeSchema>;

export default function FinancePage() {
  const [cheques, setCheques] = useState<Cheque[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [chequesRes, contactsRes] = await Promise.all([
        apiClient.get<{ total: number; items: Cheque[] }>("/finance/cheques"),
        apiClient.get<{ items: Contact[] }>("/contacts", { params: { limit: 200 } }),
      ]);
      setCheques(chequesRes.data.items);
      setContacts(contactsRes.data.items);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل بيانات الشيكات."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const contactsById = new Map(contacts.map((c) => [c.id, c]));

  const act = async (id: string, action: "deposit" | "clear" | "bounce") => {
    setActingId(id);
    try {
      await apiClient.post(`/finance/cheques/${id}/${action}`, {});
      await fetchAll();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError((axiosErr.response?.data?.detail as string) || "تعذر تنفيذ العملية.");
    } finally {
      setActingId(null);
    }
  };

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">إدارة الشيكات</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">الشيكات الواردة والصادرة، والإيداع والتحصيل.</p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit"
        >
          <Plus className="w-4 h-4" />
          شيك جديد
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            جاري التحميل...
          </div>
        ) : cheques.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <Landmark className="w-8 h-8 text-outline-variant" />
            <p className="text-body-md">لا توجد شيكات مسجّلة بعد.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">رقم الشيك</th>
                  <th className="px-6 py-4">جهة الاتصال</th>
                  <th className="px-6 py-4">النوع</th>
                  <th className="px-6 py-4">تاريخ الاستحقاق</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4">المبلغ</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {cheques.map((c) => (
                  <tr key={c.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{c.cheque_number}</td>
                    <td className="px-6 py-4 font-medium">{contactsById.get(c.contact_id)?.name ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{typeLabel[c.cheque_type]}</td>
                    <td className="px-6 py-4 text-outline">{new Date(c.due_date).toLocaleDateString("ar-EG")}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[c.status]}`}>{statusLabel[c.status]}</span>
                    </td>
                    <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">{egp(c.amount)}</td>
                    <td className="px-6 py-4">
                      {c.status === "pending" && (
                        <button
                          onClick={() => act(c.id, "deposit")}
                          disabled={actingId === c.id}
                          className="flex items-center gap-1 text-primary font-semibold text-body-sm hover:underline disabled:opacity-50"
                        >
                          <ArrowDownCircle className="w-4 h-4" /> إيداع
                        </button>
                      )}
                      {c.status === "deposited" && (
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => act(c.id, "clear")}
                            disabled={actingId === c.id}
                            className="flex items-center gap-1 text-secondary font-semibold text-body-sm hover:underline disabled:opacity-50"
                          >
                            <CheckCircle2 className="w-4 h-4" /> تحصيل
                          </button>
                          <button
                            onClick={() => act(c.id, "bounce")}
                            disabled={actingId === c.id}
                            className="flex items-center gap-1 text-error font-semibold text-body-sm hover:underline disabled:opacity-50"
                          >
                            <XCircle className="w-4 h-4" /> ارتجاع
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <CreateChequeModal
          contacts={contacts}
          onClose={() => setModalOpen(false)}
          onCreated={() => { setModalOpen(false); fetchAll(); }}
        />
      )}
    </div>
  );
}

function CreateChequeModal({
  contacts,
  onClose,
  onCreated,
}: {
  contacts: Contact[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<CreateChequeFormInput, any, CreateChequeForm>({
    resolver: zodResolver(createChequeSchema),
    defaultValues: { cheque_number: "", amount: 0, issue_date: "", due_date: "", bank_name: "", cheque_type: "incoming", contact_id: "" },
  });

  const onSubmit = async (data: CreateChequeForm) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/finance/cheques", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر إنشاء الشيك.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">شيك جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {errorMsg}
          </div>
        )}
        {contacts.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">أضف جهة اتصال واحدة على الأقل قبل تسجيل شيك.</p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="flex gap-2">
              {(["incoming", "outgoing"] as const).map((t) => (
                <label key={t} className="flex-1">
                  <input type="radio" value={t} {...register("cheque_type")} className="peer sr-only" />
                  <div className="text-center py-2.5 rounded-lg border border-outline-variant text-body-sm font-semibold text-on-surface-variant peer-checked:bg-primary peer-checked:text-on-primary peer-checked:border-primary cursor-pointer transition-colors">
                    {typeLabel[t]}
                  </div>
                </label>
              ))}
            </div>

            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">جهة الاتصال</label>
              <select {...register("contact_id")} className="input-field">
                <option value="">اختر جهة الاتصال</option>
                {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              {errors.contact_id && <p className="text-body-sm text-error">{errors.contact_id.message}</p>}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">رقم الشيك</label>
                <input {...register("cheque_number")} dir="ltr" className="input-field font-mono" />
                {errors.cheque_number && <p className="text-body-sm text-error">{errors.cheque_number.message}</p>}
              </div>
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">المبلغ</label>
                <input type="number" step="0.01" {...register("amount")} dir="ltr" className="input-field font-mono" />
                {errors.amount && <p className="text-body-sm text-error">{errors.amount.message}</p>}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">اسم البنك</label>
              <input {...register("bank_name")} className="input-field" />
              {errors.bank_name && <p className="text-body-sm text-error">{errors.bank_name.message}</p>}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">تاريخ الإصدار</label>
                <input type="date" {...register("issue_date")} dir="ltr" className="input-field font-mono" />
                {errors.issue_date && <p className="text-body-sm text-error">{errors.issue_date.message}</p>}
              </div>
              <div className="space-y-1.5">
                <label className="text-body-sm font-semibold text-on-surface-variant">تاريخ الاستحقاق</label>
                <input type="date" {...register("due_date")} dir="ltr" className="input-field font-mono" />
                {errors.due_date && <p className="text-body-sm text-error">{errors.due_date.message}</p>}
              </div>
            </div>

            <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              حفظ الشيك
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
