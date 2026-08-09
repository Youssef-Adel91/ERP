"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import {
  Search,
  Plus,
  Loader2,
  AlertCircle,
  UserRound,
  Building2,
  X,
  ChevronLeft,
} from "lucide-react";

type ContactType = "customer" | "supplier";
type ContactStatus = "active" | "blocked" | "archived";

interface Contact {
  id: string;
  contact_type: ContactType;
  status: ContactStatus;
  name: string;
  name_ar: string | null;
  phone: string | null;
  email: string | null;
  national_id: string | null;
  cod_risk_score: string | number;
  cod_rejection_count: number;
  cod_acceptance_count: number;
  created_at: string;
}

interface ContactListResponse {
  total: number;
  items: Contact[];
}

const statusLabel: Record<ContactStatus, string> = {
  active: "نشط",
  blocked: "محظور",
  archived: "مؤرشف",
};

const statusTone: Record<ContactStatus, string> = {
  active: "bg-secondary-container/30 text-secondary",
  blocked: "bg-error-container/40 text-error",
  archived: "bg-surface-container text-on-surface-variant",
};

const typeLabel: Record<ContactType, string> = {
  customer: "عميل",
  supplier: "مورّد",
};

const createContactSchema = z.object({
  contact_type: z.enum(["customer", "supplier"]),
  name: z.string().min(2, "الاسم مطلوب (حرفين على الأقل)"),
  phone: z.string().optional(),
  email: z.string().email("بريد إلكتروني غير صحيح").optional().or(z.literal("")),
});
type CreateContactForm = z.infer<typeof createContactSchema>;

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<ContactType | "">("");
  const [modalOpen, setModalOpen] = useState(false);

  const fetchContacts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<ContactListResponse>("/contacts", {
        params: {
          search: search || undefined,
          contact_type: typeFilter || undefined,
          limit: 50,
        },
      });
      setContacts(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل جهات الاتصال."));
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter]);

  useEffect(() => {
    const timeout = setTimeout(fetchContacts, 300);
    return () => clearTimeout(timeout);
  }, [fetchContacts]);

  return (
    <div className="space-y-gutter">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">جهات الاتصال</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            العملاء والموردون — {total} جهة اتصال مسجّلة.
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit"
        >
          <Plus className="w-4 h-4" />
          جهة اتصال جديدة
        </button>
      </div>

      {/* Filters */}
      <div className="glass-card rounded-xl p-4 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-outline" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ابحث بالاسم أو رقم الهاتف..."
            className="w-full pr-9 pl-4 py-2.5 bg-surface-container-low border border-outline-variant rounded-lg text-body-md outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-right"
          />
        </div>
        <div className="flex gap-2">
          {(["", "customer", "supplier"] as const).map((t) => (
            <button
              key={t || "all"}
              onClick={() => setTypeFilter(t)}
              className={`px-4 py-2.5 rounded-lg text-body-sm font-semibold transition-colors ${
                typeFilter === t
                  ? "bg-primary text-on-primary"
                  : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container"
              }`}
            >
              {t === "" ? "الكل" : typeLabel[t]}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Table */}
      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            جاري التحميل...
          </div>
        ) : contacts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <UserRound className="w-8 h-8 text-outline-variant" />
            <p className="text-body-md">لا توجد جهات اتصال مطابقة.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">الاسم</th>
                  <th className="px-6 py-4">النوع</th>
                  <th className="px-6 py-4">الهاتف</th>
                  <th className="px-6 py-4">البريد الإلكتروني</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {contacts.map((c) => (
                  <tr key={c.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-medium flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full bg-primary-container/10 text-primary flex items-center justify-center shrink-0">
                        {c.contact_type === "customer" ? <UserRound className="w-4 h-4" /> : <Building2 className="w-4 h-4" />}
                      </div>
                      {c.name}
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">{typeLabel[c.contact_type]}</td>
                    <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">{c.phone ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant" dir="ltr">{c.email ?? "—"}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[c.status]}`}>
                        {statusLabel[c.status]}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <Link
                        href={`/dashboard/contacts/${c.id}`}
                        className="flex items-center gap-1 text-primary font-semibold text-body-sm hover:underline w-fit"
                      >
                        التفاصيل
                        <ChevronLeft className="w-4 h-4 rtl:rotate-180" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <CreateContactModal
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            setModalOpen(false);
            fetchContacts();
          }}
        />
      )}
    </div>
  );
}

function CreateContactModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateContactForm>({
    resolver: zodResolver(createContactSchema),
    defaultValues: { contact_type: "customer", name: "", phone: "", email: "" },
  });

  const onSubmit = async (data: CreateContactForm) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/contacts", {
        contact_type: data.contact_type,
        name: data.name,
        phone: data.phone || undefined,
        email: data.email || undefined,
      });
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر إنشاء جهة الاتصال.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div
        className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">جهة اتصال جديدة</h3>
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

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="flex gap-2">
            {(["customer", "supplier"] as const).map((t) => (
              <label key={t} className="flex-1">
                <input type="radio" value={t} {...register("contact_type")} className="peer sr-only" />
                <div className="text-center py-2.5 rounded-lg border border-outline-variant text-body-sm font-semibold text-on-surface-variant peer-checked:bg-primary peer-checked:text-on-primary peer-checked:border-primary cursor-pointer transition-colors">
                  {typeLabel[t]}
                </div>
              </label>
            ))}
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">الاسم</label>
            <input
              {...register("name")}
              className={`w-full h-11 rounded-lg border bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right ${
                errors.name ? "border-error" : "border-outline-variant focus:border-primary focus:ring-2 focus:ring-primary/30"
              }`}
            />
            {errors.name && <p className="text-body-sm text-error">{errors.name.message}</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">الهاتف</label>
            <input
              {...register("phone")}
              dir="ltr"
              className="w-full h-11 rounded-lg border border-outline-variant bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right font-mono focus:border-primary focus:ring-2 focus:ring-primary/30"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">البريد الإلكتروني</label>
            <input
              {...register("email")}
              dir="ltr"
              className={`w-full h-11 rounded-lg border bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right font-mono ${
                errors.email ? "border-error" : "border-outline-variant focus:border-primary focus:ring-2 focus:ring-primary/30"
              }`}
            />
            {errors.email && <p className="text-body-sm text-error">{errors.email.message}</p>}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            حفظ جهة الاتصال
          </button>
        </form>
      </div>
    </div>
  );
}
