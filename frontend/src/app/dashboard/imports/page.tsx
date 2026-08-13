"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage, pickDetail } from "@/lib/api-client";
import { Ship, Plus, Loader2, AlertCircle, X, Lock } from "lucide-react";

type ImportStatus = "OPEN" | "CUSTOMS" | "CLEARED" | "CLOSED";

interface Dossier {
  id: string;
  dossier_number: string;
  supplier_id: string;
  status: ImportStatus;
  currency: string;
  fx_rate: string | number;
}
interface Contact { id: string; name: string; contact_type: "customer" | "supplier"; }

const statusLabel: Record<ImportStatus, string> = { OPEN: "مفتوح", CUSTOMS: "بالجمارك", CLEARED: "مُخلَّص", CLOSED: "مُغلق" };
const statusTone: Record<ImportStatus, string> = {
  OPEN: "bg-primary-container/10 text-primary",
  CUSTOMS: "bg-tertiary-container/10 text-tertiary",
  CLEARED: "bg-secondary-container/30 text-secondary",
  CLOSED: "bg-surface-container text-on-surface-variant",
};

const schema = z.object({
  dossier_number: z.string().min(1, "رقم الملف مطلوب"),
  supplier_id: z.string().min(1, "اختر المورد"),
  currency: z.string().min(3).max(3).default("EGP"),
  fx_rate: z.coerce.number().gt(0).default(1),
});
type FormOut = z.output<typeof schema>;
type FormIn = z.input<typeof schema>;

export default function ImportsPage() {
  const [dossiers, setDossiers] = useState<Dossier[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [dRes, cRes] = await Promise.all([
        apiClient.get<Dossier[]>("/imports/dossiers"),
        apiClient.get<{ items: Contact[] }>("/contacts", { params: { limit: 200 } }),
      ]);
      setDossiers(dRes.data);
      setContacts(cRes.data.items);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل ملفات الاستيراد."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const suppliers = contacts.filter((c) => c.contact_type === "supplier");
  const contactsById = new Map(contacts.map((c) => [c.id, c]));

  const closeDossier = async (id: string) => {
    setClosingId(id);
    try {
      await apiClient.post(`/imports/dossiers/${id}/close`, {});
      await fetchAll();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(pickDetail(axiosErr, "تعذر إغلاق الملف — تحقق من وجود مصروفات مسجلة عليه."));
    } finally {
      setClosingId(null);
    }
  };

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">ملفات الاستيراد</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">تتبع الشحنات المستوردة وتوزيع التكلفة الجمركية.</p>
        </div>
        <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
          <Plus className="w-4 h-4" /> ملف استيراد جديد
        </button>
      </div>

      {error && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>}

      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : dossiers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><Ship className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد ملفات استيراد بعد.</p></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr><th className="px-6 py-4">رقم الملف</th><th className="px-6 py-4">المورد</th><th className="px-6 py-4">العملة</th><th className="px-6 py-4">سعر الصرف</th><th className="px-6 py-4">الحالة</th><th className="px-6 py-4" /></tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {dossiers.map((d) => (
                  <tr key={d.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{d.dossier_number}</td>
                    <td className="px-6 py-4 font-medium">{contactsById.get(d.supplier_id)?.name ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{d.currency}</td>
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{Number(d.fx_rate).toFixed(4)}</td>
                    <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[d.status]}`}>{statusLabel[d.status]}</span></td>
                    <td className="px-6 py-4">
                      {d.status !== "CLOSED" && (
                        <button onClick={() => closeDossier(d.id)} disabled={closingId === d.id} className="flex items-center gap-1 text-primary font-semibold text-body-sm hover:underline disabled:opacity-50">
                          {closingId === d.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />} إغلاق وتوزيع التكلفة
                        </button>
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
        <CreateDossierModal suppliers={suppliers} onClose={() => setModalOpen(false)} onCreated={() => { setModalOpen(false); fetchAll(); }} />
      )}
    </div>
  );
}

function CreateDossierModal({ suppliers, onClose, onCreated }: { suppliers: Contact[]; onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<FormIn, any, FormOut>({
    resolver: zodResolver(schema),
    defaultValues: { dossier_number: "", supplier_id: "", currency: "EGP", fx_rate: 1 },
  });

  const onSubmit = async (data: FormOut) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/imports/dossiers", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إنشاء ملف الاستيراد."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">ملف استيراد جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        {suppliers.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">أضف مورد واحد على الأقل قبل فتح ملف استيراد.</p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">رقم الملف</label><input {...register("dossier_number")} dir="ltr" className="input-field font-mono" />{errors.dossier_number && <p className="text-body-sm text-error">{errors.dossier_number.message}</p>}</div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">المورد</label>
              <select {...register("supplier_id")} className="input-field">
                <option value="">اختر المورد</option>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {errors.supplier_id && <p className="text-body-sm text-error">{errors.supplier_id.message}</p>}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">العملة</label><input {...register("currency")} dir="ltr" className="input-field font-mono" placeholder="USD" /></div>
              <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">سعر الصرف</label><input type="number" step="0.0001" {...register("fx_rate")} dir="ltr" className="input-field font-mono" /></div>
            </div>
            <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الملف
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
