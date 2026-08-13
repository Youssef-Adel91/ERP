"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage, pickDetail } from "@/lib/api-client";
import { Workflow, Plus, Loader2, AlertCircle, X, Plane, BedDouble, Car, UserSearch, ArrowLeftRight } from "lucide-react";

interface Stage { id: string; label: string; label_ar?: string; order: number; is_terminal?: boolean; }
interface CaseType {
  id: string;
  code: string;
  name: string;
  name_ar: string | null;
  plugin_key: string;
  initial_stage: string;
  stages: Stage[];
}
interface Case {
  id: string;
  case_type_id: string;
  title: string | null;
  current_stage: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
}

const pluginMeta: Record<string, { label: string; icon: React.ElementType; bootstrapPath: string }> = {
  travel: { label: "السياحة والسفر", icon: Plane, bootstrapPath: "/travel/bootstrap" },
  hospitality: { label: "الضيافة والفنادق", icon: BedDouble, bootstrapPath: "/hospitality/bootstrap" },
  rental: { label: "تأجير السيارات", icon: Car, bootstrapPath: "/rental/bootstrap" },
  recruitment: { label: "التوظيف والاستقدام", icon: UserSearch, bootstrapPath: "/recruitment/bootstrap" },
};

const schema = z.object({
  case_type_id: z.string().min(1, "اختر النوع"),
  title: z.string().min(1, "العنوان مطلوب"),
});
type Form = z.infer<typeof schema>;

export default function CasesPage() {
  const router = useRouter();
  const [caseTypes, setCaseTypes] = useState<CaseType[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);
  const [transitioning, setTransitioning] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [typesRes, casesRes] = await Promise.all([
        apiClient.get<CaseType[]>("/case-types"),
        apiClient.get<Case[]>("/cases"),
      ]);
      setCaseTypes(typesRes.data);
      setCases(casesRes.data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل الحالات."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const caseTypesById = new Map(caseTypes.map((t) => [t.id, t]));
  const activatedPlugins = new Set(caseTypes.map((t) => t.plugin_key));

  const activatePlugin = async (key: string) => {
    setActivating(key);
    try {
      await apiClient.post(pluginMeta[key].bootstrapPath, {});
      await fetchAll();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(pickDetail(axiosErr, "تعذر تفعيل الموديول."));
    } finally {
      setActivating(null);
    }
  };

  const transitionCase = async (c: Case, toStage: string) => {
    setTransitioning(c.id);
    try {
      await apiClient.post(`/cases/${c.id}/transition`, { to_stage: toStage });
      await fetchAll();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(pickDetail(axiosErr, "تعذر نقل الحالة للمرحلة الجديدة."));
    } finally {
      setTransitioning(null);
    }
  };

  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">محرك الحالات والحجوزات</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">يشغّل السياحة، الضيافة، تأجير السيارات، والتوظيف بنفس المحرك.</p>
      </div>

      {error && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>}

      {/* Plugin activation */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-gutter">
        {Object.entries(pluginMeta).map(([key, meta]) => {
          const active = activatedPlugins.has(key);
          return (
            <div key={key} className="glass-card rounded-xl p-card-padding flex flex-col items-start gap-3">
              <div className="w-10 h-10 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
                <meta.icon className="w-5 h-5" />
              </div>
              <h4 className="font-headline-sm text-headline-sm text-on-surface">{meta.label}</h4>
              {active ? (
                <span className="px-2 py-1 rounded text-[11px] font-bold bg-secondary-container/30 text-secondary">مُفعّل</span>
              ) : (
                <button
                  onClick={() => activatePlugin(key)}
                  disabled={activating === key}
                  className="text-primary font-semibold text-body-sm hover:underline disabled:opacity-50"
                >
                  {activating === key ? "جاري التفعيل..." : "تفعيل الموديول"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex justify-between items-center">
        <h2 className="font-headline-sm text-headline-sm text-on-surface">الحالات المفتوحة</h2>
        <button onClick={() => setModalOpen(true)} disabled={caseTypes.length === 0} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
          <Plus className="w-4 h-4" /> حالة جديدة
        </button>
      </div>

      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : cases.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><Workflow className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد حالات مفتوحة بعد. فعّل موديول وابدأ حالة جديدة.</p></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr><th className="px-6 py-4">العنوان</th><th className="px-6 py-4">النوع</th><th className="px-6 py-4">المرحلة الحالية</th><th className="px-6 py-4">الحالة</th><th className="px-6 py-4" /></tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {cases.map((c) => {
                  const type = caseTypesById.get(c.case_type_id);
                  const stage = type?.stages.find((s) => s.id === c.current_stage);
                  const nextStages = (type?.stages ?? []).filter((s) => s.id !== c.current_stage);
                  return (
                    <tr
                      key={c.id}
                      onClick={() => router.push(`/dashboard/cases/${c.id}`)}
                      className="hover:bg-surface-container-lowest transition-colors cursor-pointer"
                    >
                      <td className="px-6 py-4 font-medium">{c.title ?? "—"}</td>
                      <td className="px-6 py-4 text-on-surface-variant">{type?.name_ar ?? type?.name ?? "—"}</td>
                      <td className="px-6 py-4"><span className="px-2 py-1 rounded text-[11px] font-bold bg-primary-container/10 text-primary">{stage?.label_ar ?? stage?.label ?? c.current_stage}</span></td>
                      <td className="px-6 py-4 text-on-surface-variant">{c.status}</td>
                      <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                        {nextStages.length > 0 && (
                          <div className="flex items-center gap-2">
                            <ArrowLeftRight className="w-3.5 h-3.5 text-outline shrink-0" />
                            <select
                              disabled={transitioning === c.id}
                              defaultValue=""
                              onChange={(e) => { if (e.target.value) transitionCase(c, e.target.value); }}
                              className="text-body-sm bg-surface-container-low border border-outline-variant rounded-lg px-2 py-1.5 outline-none"
                            >
                              <option value="" disabled>نقل إلى...</option>
                              {nextStages.map((s) => <option key={s.id} value={s.id}>{s.label_ar ?? s.label}</option>)}
                            </select>
                          </div>
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
        <CreateCaseModal caseTypes={caseTypes} onClose={() => setModalOpen(false)} onCreated={() => { setModalOpen(false); fetchAll(); }} />
      )}
    </div>
  );
}

function CreateCaseModal({ caseTypes, onClose, onCreated }: { caseTypes: CaseType[]; onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { case_type_id: "", title: "" },
  });

  const onSubmit = async (data: Form) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/cases", { case_type_id: data.case_type_id, title: data.title, data: {} });
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر فتح الحالة."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">حالة جديدة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">النوع</label>
            <select {...register("case_type_id")} className="input-field">
              <option value="">اختر النوع</option>
              {caseTypes.map((t) => <option key={t.id} value={t.id}>{t.name_ar ?? t.name}</option>)}
            </select>
            {errors.case_type_id && <p className="text-body-sm text-error">{errors.case_type_id.message}</p>}
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">العنوان</label>
            <input {...register("title")} className="input-field" />
            {errors.title && <p className="text-body-sm text-error">{errors.title.message}</p>}
          </div>
          <p className="text-body-sm text-on-surface-variant">تفاصيل كل مرحلة (بيانات المسافر، الغرفة، السيارة...) بتتضاف من صفحة تفاصيل الحالة لاحقًا.</p>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} فتح الحالة
          </button>
        </form>
      </div>
    </div>
  );
}
