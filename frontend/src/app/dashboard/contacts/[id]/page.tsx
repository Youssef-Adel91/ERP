"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import {
  ArrowRight,
  UserRound,
  Building2,
  Phone,
  Mail,
  IdCard,
  Loader2,
  AlertCircle,
  ShieldCheck,
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

export default function ContactDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [contact, setContact] = useState<Contact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const { data } = await apiClient.get<Contact>(`/contacts/${params.id}`);
        if (!cancelled) setContact(data);
      } catch {
        if (!cancelled) setError("جهة الاتصال غير موجودة أو تعذر تحميل بياناتها.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  return (
    <div className="space-y-gutter">
      <button
        onClick={() => router.push("/dashboard/contacts")}
        className="flex items-center gap-1 text-primary font-semibold text-body-sm hover:underline w-fit"
      >
        <ArrowRight className="w-4 h-4 rtl:rotate-180" />
        رجوع لجهات الاتصال
      </button>

      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          جاري التحميل...
        </div>
      ) : error || !contact ? (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error || "جهة الاتصال غير موجودة."}
        </div>
      ) : (
        <>
          {/* Header card */}
          <div className="glass-card rounded-xl p-card-padding flex flex-col sm:flex-row items-start sm:items-center gap-6">
            <div className="w-16 h-16 rounded-xl bg-primary-container/10 text-primary flex items-center justify-center shrink-0">
              {contact.contact_type === "customer" ? <UserRound className="w-8 h-8" /> : <Building2 className="w-8 h-8" />}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="font-headline-lg text-headline-lg text-on-surface">{contact.name}</h1>
                <span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[contact.status]}`}>
                  {statusLabel[contact.status]}
                </span>
              </div>
              <p className="text-body-md text-on-surface-variant mt-1">{typeLabel[contact.contact_type]}</p>
            </div>
          </div>

          {/* Details grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
            <div className="lg:col-span-2 glass-card rounded-xl p-card-padding space-y-6">
              <h4 className="font-headline-sm text-headline-sm text-on-surface">بيانات التواصل</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <InfoRow icon={Phone} label="الهاتف" value={contact.phone ?? "—"} dir="ltr" />
                <InfoRow icon={Mail} label="البريد الإلكتروني" value={contact.email ?? "—"} dir="ltr" />
                <InfoRow icon={IdCard} label="الرقم القومي" value={contact.national_id ?? "—"} dir="ltr" />
                <InfoRow
                  icon={UserRound}
                  label="تاريخ الإضافة"
                  value={new Date(contact.created_at).toLocaleDateString("ar-EG")}
                />
              </div>
            </div>

            {/* COD trust card */}
            <div className="glass-card rounded-xl p-card-padding space-y-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                <h4 className="font-headline-sm text-headline-sm text-on-surface">مؤشر الثقة (COD)</h4>
              </div>
              <div>
                <div className="flex justify-between text-body-sm mb-2">
                  <span className="text-on-surface-variant">درجة المخاطرة</span>
                  <span className="font-data-mono font-bold" dir="ltr">
                    {(Number(contact.cod_risk_score) * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="w-full bg-surface-container rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${Number(contact.cod_risk_score) > 0.5 ? "bg-error" : "bg-secondary"}`}
                    style={{ width: `${Number(contact.cod_risk_score) * 100}%` }}
                  />
                </div>
              </div>
              <div className="flex justify-between text-body-sm pt-2 border-t border-outline-variant">
                <span className="text-secondary font-semibold">{contact.cod_acceptance_count} استلام ناجح</span>
                <span className="text-error font-semibold">{contact.cod_rejection_count} رفض</span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function InfoRow({
  icon: Icon,
  label,
  value,
  dir,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  dir?: "ltr" | "rtl";
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-9 h-9 rounded-lg bg-surface-container-low text-on-surface-variant flex items-center justify-center shrink-0">
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <p className="text-body-sm text-outline">{label}</p>
        <p className="text-body-md font-medium text-on-surface" dir={dir}>{value}</p>
      </div>
    </div>
  );
}
