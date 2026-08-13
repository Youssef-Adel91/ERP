"use client";

import { useState, Suspense, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { Card } from "@/components/ui/Card";
import {
  ArrowRight,
  Loader2,
  AlertCircle,
  Plane,
  Users2,
  Calendar,
  Wallet,
} from "lucide-react";

interface PackageDetail {
  id: string;
  name_ar: string;
  destination: string;
  duration_days: number;
  duration_nights: number;
  base_price: number;
  base_cost: number;
  currency: string;
  min_pax: number;
  max_pax: number | null;
  components: { description: string; component_type: string; sell_price: number; quantity: number }[];
}

interface CaseType {
  id: string;
  code: string;
  plugin_key: string;
}

const egp = (v: number, currency = "EGP") =>
  `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ${currency === "EGP" ? "ج.م" : currency}`;

function NewBookingInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const packageId = searchParams.get("package_id");

  const [customerName, setCustomerName] = useState("");
  const [customerNameAr, setCustomerNameAr] = useState("");
  const [travelDate, setTravelDate] = useState("");
  const [returnDate, setReturnDate] = useState("");
  const [groupSize, setGroupSize] = useState<number | "">("");
  const [destination, setDestination] = useState("");
  const [notes, setNotes] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const { data: pkg } = useQuery({
    queryKey: ["travel-package", packageId],
    enabled: !!packageId,
    queryFn: async () => {
      const res = await apiClient.get<PackageDetail>(`/travel/packages/${packageId}`);
      return res.data;
    },
  });

  const { data: caseTypes } = useQuery({
    queryKey: ["case-types", "travel"],
    enabled: !packageId,
    queryFn: async () => {
      const res = await apiClient.get<CaseType[]>("/case-types", { params: { plugin_key: "travel" } });
      return res.data;
    },
  });
  const caseType = caseTypes?.find((c) => c.code === "travel_booking");

  const bookFromPackage = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/travel/packages/${packageId}/book`, {
        customer_name: customerName,
        customer_name_ar: customerNameAr || undefined,
        travel_date_requested: travelDate,
        return_date_requested: returnDate || undefined,
        group_size: groupSize || undefined,
        notes: notes || undefined,
      });
      return res.data;
    },
    onSuccess: (data) => router.push(`/dashboard/cases/${data.id}`),
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إنشاء الحجز.")),
  });

  const bookCustom = useMutation({
    mutationFn: async () => {
      if (!caseType) throw new Error("no case type");
      const res = await apiClient.post("/cases", {
        case_type_id: caseType.id,
        title: `${destination} — ${customerName}`,
        start_date: travelDate || undefined,
        data: {
          customer_name: customerName,
          customer_name_ar: customerNameAr || undefined,
          destination,
          travel_date_requested: travelDate,
          return_date_requested: returnDate || undefined,
          group_size: groupSize || 1,
          trip_type: "package",
          services: [],
          currency: "EGP",
          notes: notes || undefined,
        },
      });
      return res.data;
    },
    onSuccess: (data) => router.push(`/dashboard/cases/${data.id}`),
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إنشاء الحجز.")),
  });

  const submitting = bookFromPackage.isPending || bookCustom.isPending;
  const canSubmit = customerName && travelDate && (packageId ? true : destination);

  return (
    <div className="space-y-gutter max-w-2xl">
      <div className="flex items-center gap-3">
        <Link href="/dashboard/travel" className="text-on-surface-variant hover:text-on-surface">
          <ArrowRight className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">حجز جديد</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            {packageId ? "بيع باقة جاهزة لعميل" : "حجز مخصّص بدون باقة"}
          </p>
        </div>
      </div>

      {packageId && pkg && (
        <Card>
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-headline-sm text-headline-sm text-on-surface flex items-center gap-1.5">
                <Plane className="w-4 h-4 text-primary" /> {pkg.name_ar}
              </h3>
              <p className="text-body-sm text-on-surface-variant mt-1 flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {pkg.duration_days} أيام / {pkg.duration_nights} ليالي — {pkg.destination}</p>
              <p className="text-body-sm text-on-surface-variant mt-1 flex items-center gap-1"><Users2 className="w-3.5 h-3.5" /> {pkg.min_pax}{pkg.max_pax ? `–${pkg.max_pax}` : "+"} فرد</p>
            </div>
            <div className="text-left">
              <p className="text-[11px] text-on-surface-variant">سعر الباقة</p>
              <p className="font-data-mono font-bold text-headline-sm text-on-surface" dir="ltr">{egp(pkg.base_price, pkg.currency)}</p>
              <p className="text-[11px] text-secondary flex items-center gap-1 justify-end"><Wallet className="w-3 h-3" /> هامش {egp(pkg.base_price - pkg.base_cost, pkg.currency)}</p>
            </div>
          </div>
          {pkg.components?.length > 0 && (
            <ul className="mt-3 pt-3 border-t border-outline-variant/40 space-y-1 text-body-sm text-on-surface-variant">
              {pkg.components.map((c, i) => <li key={i}>• {c.description || c.component_type}</li>)}
            </ul>
          )}
        </Card>
      )}

      <Card className="space-y-3">
        <Field label="اسم العميل *">
          <input className="input" value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
        </Field>
        <Field label="اسم العميل بالعربي (اختياري)">
          <input className="input" value={customerNameAr} onChange={(e) => setCustomerNameAr(e.target.value)} />
        </Field>
        {!packageId && (
          <Field label="الوجهة *">
            <input className="input" value={destination} onChange={(e) => setDestination(e.target.value)} />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="تاريخ السفر *">
            <input type="date" className="input" value={travelDate} onChange={(e) => setTravelDate(e.target.value)} />
          </Field>
          <Field label="تاريخ العودة">
            <input type="date" className="input" value={returnDate} onChange={(e) => setReturnDate(e.target.value)} />
          </Field>
        </div>
        <Field label="عدد الأفراد">
          <input type="number" min={1} className="input" value={groupSize} onChange={(e) => setGroupSize(e.target.value ? Number(e.target.value) : "")} />
        </Field>
        <Field label="ملاحظات">
          <textarea className="input min-h-20" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>

        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}

        <button
          onClick={() => (packageId ? bookFromPackage.mutate() : bookCustom.mutate())}
          disabled={!canSubmit || submitting}
          className="w-full h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          تأكيد الحجز
        </button>
      </Card>

      <style jsx global>{`
        .input {
          height: 2.5rem;
          border-radius: 0.5rem;
          border: 1px solid var(--outline-variant);
          padding: 0 0.75rem;
          font-size: 0.875rem;
          background: var(--surface);
          color: var(--on-surface);
          width: 100%;
        }
        textarea.input { height: auto; padding: 0.5rem 0.75rem; }
      `}</style>
    </div>
  );
}

export default function NewTravelBookingPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center py-16"><Loader2 className="w-5 h-5 animate-spin" /></div>}>
      <NewBookingInner />
    </Suspense>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">{label}</span>
      {children}
    </label>
  );
}
