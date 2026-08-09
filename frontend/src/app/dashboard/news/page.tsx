"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { useAppStore } from "@/store/use-app-store";
import { Megaphone, Plus, Loader2, AlertCircle, X } from "lucide-react";

interface Announcement {
  id: string;
  title: string;
  content: string;
  created_by: string | null;
  created_at: string;
}

const schema = z.object({
  title: z.string().min(2, "العنوان مطلوب"),
  content: z.string().min(5, "المحتوى قصير جدًا"),
});
type Form = z.infer<typeof schema>;

export default function NewsPage() {
  const { user } = useAppStore();
  const [items, setItems] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<Announcement[]>("/news/");
      setItems(data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل الأخبار."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const isOwner = user?.role === "OWNER" || user?.role === "admin";

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الأخبار والإعلانات</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">إعلانات داخلية لكل فريق العمل.</p>
        </div>
        {isOwner && (
          <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
            <Plus className="w-4 h-4" /> إعلان جديد
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
      ) : items.length === 0 ? (
        <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
          <Megaphone className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد إعلانات بعد.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((a) => (
            <div key={a.id} className="glass-card rounded-xl p-card-padding">
              <div className="flex justify-between items-start gap-4 mb-2">
                <h3 className="font-headline-sm text-headline-sm text-on-surface">{a.title}</h3>
                <span className="text-body-sm text-outline shrink-0">{new Date(a.created_at).toLocaleDateString("ar-EG")}</span>
              </div>
              <p className="text-body-md text-on-surface-variant whitespace-pre-wrap">{a.content}</p>
            </div>
          ))}
        </div>
      )}

      {modalOpen && (
        <CreateAnnouncementModal onClose={() => setModalOpen(false)} onCreated={() => { setModalOpen(false); fetchAll(); }} />
      )}
    </div>
  );
}

function CreateAnnouncementModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", content: "" },
  });

  const onSubmit = async (data: Form) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/news/", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر نشر الإعلان.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">إعلان جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">العنوان</label>
            <input {...register("title")} className="input-field" />
            {errors.title && <p className="text-body-sm text-error">{errors.title.message}</p>}
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">المحتوى</label>
            <textarea {...register("content")} rows={4} className="input-field h-auto py-2.5" />
            {errors.content && <p className="text-body-sm text-error">{errors.content.message}</p>}
          </div>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} نشر الإعلان
          </button>
        </form>
      </div>
    </div>
  );
}
