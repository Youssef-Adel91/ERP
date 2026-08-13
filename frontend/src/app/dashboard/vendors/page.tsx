"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  Building2,
  Plus,
  Loader2,
  AlertCircle,
  X,
  Tags,
  CheckCircle2,
} from "lucide-react";

/**
 * Vendor & Rate Card management — the B2B supply side (airlines, hotels,
 * visa agencies, transport, medical centers) that Travel/Recruitment
 * bookings reference in their services[] line items today only as free
 * text (supplier_name). This gives Karim/Amira a structured place to keep
 * negotiated buy prices, so the internal cost is looked up rather than
 * re-typed on every booking. GET /cases/vendors/rates is the lookup the
 * Generic Case Engine's dynamic form could call in the future when a
 * service_type is picked — not wired into that form yet, per the explicit
 * scope of this task (management UI only).
 */

const vendorTypeLabel: Record<string, string> = {
  AIRLINE: "شركة طيران",
  HOTEL: "فندق",
  VISA_AGENCY: "وكالة تأشيرات",
  TRANSPORT: "نقل ومواصلات",
  TOUR_OPERATOR: "مشغّل رحلات",
  MEDICAL_CENTER: "مركز طبي",
  INSURANCE: "تأمين",
  OTHER: "أخرى",
};

interface Vendor {
  id: string;
  name: string;
  name_ar: string | null;
  vendor_type: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  notes: string | null;
  is_active: boolean;
}

interface RateCard {
  id: string;
  vendor_id: string;
  service_type: string;
  description: string | null;
  buy_price: string;
  currency: string;
  valid_from: string;
  valid_until: string | null;
  cancellation_policy: string | null;
  is_active: boolean;
}

export default function VendorsPage() {
  const [selectedVendor, setSelectedVendor] = useState<Vendor | null>(null);
  const [vendorModalOpen, setVendorModalOpen] = useState(false);
  const [rateModalOpen, setRateModalOpen] = useState(false);

  const { data: vendors, isLoading, isError } = useQuery({
    queryKey: ["vendors"],
    queryFn: async () => {
      const res = await apiClient.get<Vendor[]>("/cases/vendors");
      return res.data;
    },
  });

  const selectedVendorId = selectedVendor?.id;
  const { data: rateCards, isLoading: ratesLoading } = useQuery({
    queryKey: ["vendor-rates", selectedVendorId],
    // Guard on the captured id (not a `!` assertion on selectedVendor) so
    // there's no risk of a stale closure referencing a cleared selection
    // if the query somehow fires after selectedVendor changes.
    queryFn: async () => {
      if (!selectedVendorId) return [];
      const res = await apiClient.get<RateCard[]>(`/cases/vendors/${selectedVendorId}/rates`);
      return res.data;
    },
    enabled: !!selectedVendorId,
  });

  return (
    <div className="space-y-gutter">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الموردين والأسعار</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            ملفات الموردين (طيران، فنادق، تأشيرات، نقل) وأسعار الشراء المتفق عليها لكل خدمة.
          </p>
        </div>
        <button
          onClick={() => setVendorModalOpen(true)}
          className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity"
        >
          <Plus className="w-4 h-4" /> مورد جديد
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter items-start">
        {/* Vendor list */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="p-card-padding border-b border-outline-variant">
            <h2 className="font-headline-sm text-headline-sm text-on-surface">الموردون</h2>
          </div>
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-on-surface-variant gap-2">
              <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-body-sm text-error">
              <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الموردين.
            </div>
          ) : !vendors || vendors.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-on-surface-variant gap-2">
              <Building2 className="w-7 h-7 text-outline-variant" />
              <p className="text-body-sm">لا يوجد موردون بعد.</p>
            </div>
          ) : (
            <div className="divide-y divide-outline-variant/30 max-h-[65vh] overflow-y-auto">
              {vendors.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setSelectedVendor(v)}
                  className={`w-full text-right px-4 py-3 hover:bg-surface-container-lowest transition-colors ${
                    selectedVendor?.id === v.id ? "bg-primary-container/10" : ""
                  }`}
                >
                  <p className="text-body-md font-medium text-on-surface">{v.name_ar ?? v.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-surface-container text-on-surface-variant">
                      {vendorTypeLabel[v.vendor_type] ?? v.vendor_type}
                    </span>
                    {!v.is_active && (
                      <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-error-container text-on-error-container">
                        غير نشط
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Rate cards for selected vendor */}
        <div className="lg:col-span-2 glass-card rounded-xl overflow-hidden">
          <div className="p-card-padding border-b border-outline-variant flex items-center justify-between">
            <div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface">
                {selectedVendor ? `أسعار ${selectedVendor.name_ar ?? selectedVendor.name}` : "سجل الأسعار"}
              </h2>
              {selectedVendor && (
                <p className="text-body-sm text-on-surface-variant mt-0.5">
                  {selectedVendor.contact_person ?? "—"} ·{" "}
                  <span className="font-data-mono" dir="ltr">{selectedVendor.phone ?? "—"}</span>
                </p>
              )}
            </div>
            {selectedVendor && (
              <button
                onClick={() => setRateModalOpen(true)}
                className="flex items-center gap-2 h-9 px-3 rounded-lg border border-primary text-primary font-semibold text-body-sm hover:bg-primary-container/10 transition-colors"
              >
                <Tags className="w-4 h-4" /> إضافة سعر
              </button>
            )}
          </div>

          {!selectedVendor ? (
            <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
              <Tags className="w-7 h-7 text-outline-variant" />
              <p className="text-body-sm">اختر موردًا من القائمة لعرض أسعاره.</p>
            </div>
          ) : ratesLoading ? (
            <div className="flex items-center justify-center py-12 text-on-surface-variant gap-2">
              <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
            </div>
          ) : !rateCards || rateCards.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
              <Tags className="w-7 h-7 text-outline-variant" />
              <p className="text-body-sm">لا توجد أسعار مسجّلة لهذا المورد بعد.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-right">
                <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                  <tr>
                    <th className="px-4 py-3">نوع الخدمة</th>
                    <th className="px-4 py-3">الوصف</th>
                    <th className="px-4 py-3">سعر الشراء</th>
                    <th className="px-4 py-3">صالح من</th>
                    <th className="px-4 py-3">صالح حتى</th>
                    <th className="px-4 py-3">الحالة</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30 text-body-md">
                  {rateCards.map((r) => (
                    <tr key={r.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-4 py-3 font-medium">{r.service_type}</td>
                      <td className="px-4 py-3 text-on-surface-variant">{r.description ?? "—"}</td>
                      <td className="px-4 py-3 font-data-mono" dir="ltr">{r.buy_price} {r.currency}</td>
                      <td className="px-4 py-3 font-data-mono text-on-surface-variant" dir="ltr">{r.valid_from}</td>
                      <td className="px-4 py-3 font-data-mono text-on-surface-variant" dir="ltr">{r.valid_until ?? "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded text-[11px] font-bold ${r.is_active ? "bg-success-bg text-success" : "bg-surface-container text-on-surface-variant"}`}>
                          {r.is_active ? "نشط" : "موقوف"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {vendorModalOpen && <CreateVendorModal onClose={() => setVendorModalOpen(false)} />}
      {rateModalOpen && selectedVendor && (
        <CreateRateCardModal vendor={selectedVendor} onClose={() => setRateModalOpen(false)} />
      )}
    </div>
  );
}

// ── Create Vendor ──────────────────────────────────────────────────────────────

const vendorSchema = z.object({
  name: z.string().min(1, "الاسم مطلوب"),
  name_ar: z.string().optional(),
  vendor_type: z.string().min(1),
  contact_person: z.string().optional(),
  phone: z.string().optional(),
  email: z.string().optional(),
  notes: z.string().optional(),
});
type VendorForm = z.infer<typeof vendorSchema>;

function CreateVendorModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors } } = useForm<VendorForm>({
    resolver: zodResolver(vendorSchema),
    defaultValues: { name: "", name_ar: "", vendor_type: "OTHER", contact_person: "", phone: "", email: "", notes: "" },
  });

  const mutation = useMutation({
    mutationFn: async (data: VendorForm) => {
      await apiClient.post("/cases/vendors", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vendors"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-5">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">مورد جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {mutation.isError && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {pickDetail(mutation.error, "تعذر إنشاء المورد.")}
          </div>
        )}
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الاسم</label>
              <input {...register("name")} className="input-field" />
              {errors.name && <p className="text-body-sm text-error">{errors.name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الاسم بالعربي</label>
              <input {...register("name_ar")} className="input-field" />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">النوع</label>
            <select {...register("vendor_type")} className="input-field">
              {Object.entries(vendorTypeLabel).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">مسؤول التواصل</label>
              <input {...register("contact_person")} className="input-field" />
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الهاتف</label>
              <input {...register("phone")} dir="ltr" className="input-field font-mono" />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">البريد الإلكتروني</label>
            <input {...register("email")} dir="ltr" className="input-field font-mono" />
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
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} إنشاء المورد
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Create Rate Card ──────────────────────────────────────────────────────────

const rateSchema = z.object({
  service_type: z.string().min(1, "نوع الخدمة مطلوب"),
  description: z.string().optional(),
  buy_price: z.string().min(1, "سعر الشراء مطلوب"),
  currency: z.string().min(1),
  valid_from: z.string().optional(),
  valid_until: z.string().optional(),
  cancellation_policy: z.string().optional(),
});
type RateForm = z.infer<typeof rateSchema>;

function CreateRateCardModal({ vendor, onClose }: { vendor: Vendor; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [success, setSuccess] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm<RateForm>({
    resolver: zodResolver(rateSchema),
    defaultValues: { service_type: "", description: "", buy_price: "", currency: "EGP", valid_from: "", valid_until: "", cancellation_policy: "" },
  });

  const mutation = useMutation({
    mutationFn: async (data: RateForm) => {
      await apiClient.post(`/cases/vendors/${vendor.id}/rates`, {
        ...data,
        buy_price: Number(data.buy_price),
        valid_from: data.valid_from || undefined,
        valid_until: data.valid_until || undefined,
      });
    },
    onSuccess: () => {
      setSuccess(true);
      queryClient.invalidateQueries({ queryKey: ["vendor-rates", vendor.id] });
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-5">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">سعر جديد — {vendor.name_ar ?? vendor.name}</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {success && (
          <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg mb-4 text-body-sm font-medium border border-success">
            <CheckCircle2 className="w-4 h-4 shrink-0" /> تم إضافة السعر. أضف سعرًا آخر أو أغلق النافذة.
          </div>
        )}
        {mutation.isError && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {pickDetail(mutation.error, "تعذر إضافة السعر.")}
          </div>
        )}

        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">نوع الخدمة</label>
            <input {...register("service_type")} dir="ltr" className="input-field font-mono" placeholder="flight / hotel / visa / transfer ..." />
            {errors.service_type && <p className="text-body-sm text-error">{errors.service_type.message}</p>}
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">الوصف</label>
            <input {...register("description")} className="input-field" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">سعر الشراء</label>
              <input {...register("buy_price")} type="number" step="0.01" dir="ltr" className="input-field font-mono" />
              {errors.buy_price && <p className="text-body-sm text-error">{errors.buy_price.message}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">العملة</label>
              <input {...register("currency")} dir="ltr" className="input-field font-mono" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">صالح من</label>
              <input {...register("valid_from")} type="date" dir="ltr" className="input-field font-mono" />
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">صالح حتى</label>
              <input {...register("valid_until")} type="date" dir="ltr" className="input-field font-mono" />
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">شروط الإلغاء</label>
            <textarea {...register("cancellation_policy")} rows={2} className="input-field" />
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ السعر
          </button>
        </form>
      </div>
    </div>
  );
}
