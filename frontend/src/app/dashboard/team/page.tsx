"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { useAppStore } from "@/store/use-app-store";
import { UsersRound, Plus, Loader2, AlertCircle, X } from "lucide-react";

type UserRole = "OWNER" | "ADMIN" | "STAFF" | "SALES" | "ACCOUNTING";

interface TeamMember {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

const roleLabel: Record<UserRole, string> = {
  OWNER: "مالك", ADMIN: "مدير", STAFF: "موظف", SALES: "مبيعات", ACCOUNTING: "محاسبة",
};
const roleTone: Record<UserRole, string> = {
  OWNER: "bg-primary-container/10 text-primary",
  ADMIN: "bg-tertiary-container/10 text-tertiary",
  STAFF: "bg-surface-container text-on-surface-variant",
  SALES: "bg-secondary-container/30 text-secondary",
  ACCOUNTING: "bg-secondary-container/30 text-secondary",
};

const schema = z.object({
  full_name: z.string().min(2, "الاسم مطلوب"),
  email: z.string().email("بريد إلكتروني غير صحيح"),
  password: z.string().min(8, "كلمة المرور 8 أحرف على الأقل"),
  role: z.enum(["ADMIN", "STAFF", "SALES", "ACCOUNTING"]),
});
type Form = z.infer<typeof schema>;

export default function TeamPage() {
  const { user } = useAppStore();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<TeamMember[]>("/team/");
      setMembers(data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل أعضاء الفريق."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const isOwner = user?.role === "OWNER";

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">فريق العمل</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">مستخدمو النظام وصلاحياتهم.</p>
        </div>
        {isOwner && (
          <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
            <Plus className="w-4 h-4" /> عضو جديد
          </button>
        )}
      </div>

      {error && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>}

      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr><th className="px-6 py-4">الاسم</th><th className="px-6 py-4">البريد الإلكتروني</th><th className="px-6 py-4">الصلاحية</th><th className="px-6 py-4">الحالة</th></tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {members.map((m) => (
                  <tr key={m.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-medium">{m.full_name}</td>
                    <td className="px-6 py-4 text-on-surface-variant" dir="ltr">{m.email}</td>
                    <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${roleTone[m.role]}`}>{roleLabel[m.role]}</span></td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-[11px] font-bold ${m.is_active ? "bg-secondary-container/30 text-secondary" : "bg-error-container/40 text-error"}`}>
                        {m.is_active ? "نشط" : "معطل"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <InviteMemberModal onClose={() => setModalOpen(false)} onCreated={() => { setModalOpen(false); fetchAll(); }} />
      )}
    </div>
  );
}

function InviteMemberModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "", role: "STAFF" },
  });

  const onSubmit = async (data: Form) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/team/", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر إضافة العضو.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">عضو جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الاسم بالكامل</label><input {...register("full_name")} className="input-field" />{errors.full_name && <p className="text-body-sm text-error">{errors.full_name.message}</p>}</div>
          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">البريد الإلكتروني</label><input {...register("email")} dir="ltr" className="input-field font-mono" />{errors.email && <p className="text-body-sm text-error">{errors.email.message}</p>}</div>
          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">كلمة المرور المبدئية</label><input type="password" {...register("password")} dir="ltr" className="input-field font-mono" />{errors.password && <p className="text-body-sm text-error">{errors.password.message}</p>}</div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">الصلاحية</label>
            <select {...register("role")} className="input-field">
              <option value="ADMIN">مدير</option>
              <option value="STAFF">موظف</option>
              <option value="SALES">مبيعات</option>
              <option value="ACCOUNTING">محاسبة</option>
            </select>
          </div>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} إضافة العضو
          </button>
        </form>
      </div>
    </div>
  );
}
