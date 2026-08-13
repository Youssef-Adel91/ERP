"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  Truck,
  Plus,
  Loader2,
  AlertCircle,
  X,
  Eye,
  EyeOff,
  CheckCircle2,
  Ban,
  ExternalLink,
  Package,
} from "lucide-react";

/**
 * Shipping Hub — carrier account configuration (Bosta/Mylerz credentials,
 * stored by Vault reference only — same convention as the WhatsApp
 * Integration card in Settings) plus a read-only feed of shipments created
 * from the Sales page's "شحن" (Ship) action. The actual Ship action lives
 * on the Sales invoices table (dashboard/sales/page.tsx) since that's
 * where a physical, POSTED order naturally becomes a waybill — this page
 * is where the merchant sets carriers up first and then watches AWBs move.
 */

const carrierLabel: Record<string, string> = {
  bosta: "بوسطة (Bosta)",
  mylerz: "ميلرز (Mylerz)",
};

const stateLabel: Record<string, string> = {
  created: "تم الإنشاء",
  picked_up: "تم الاستلام من التاجر",
  in_transit: "في الطريق",
  out_for_delivery: "خارج للتسليم",
  delivered: "تم التسليم",
  returning: "عائدة",
  returned: "تم الإرجاع",
  lost: "مفقودة",
  cancelled: "ملغاة",
};
const stateTone: Record<string, string> = {
  created: "bg-surface-container text-on-surface-variant",
  picked_up: "bg-primary-container/10 text-primary",
  in_transit: "bg-primary-container/10 text-primary",
  out_for_delivery: "bg-warning-bg text-warning",
  delivered: "bg-success-bg text-success",
  returning: "bg-warning-bg text-warning",
  returned: "bg-error-container text-on-error-container",
  lost: "bg-error-container text-on-error-container",
  cancelled: "bg-surface-container text-on-surface-variant",
};

interface AvailableCarrier { code: string; label: string; }
interface CarrierAccount {
  id: string;
  carrier_code: string;
  credentials_ref: string;
  webhook_secret_ref: string;
  is_active: boolean;
}
interface Shipment {
  id: string;
  invoice_id: string;
  carrier_code: string;
  awb_number: string;
  tracking_url: string | null;
  state: string;
  cod_amount: string | number;
  return_received_at: string | null;
}

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

export default function ShippingPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");

  const { data: accounts, isLoading: accountsLoading } = useQuery({
    queryKey: ["carrier-accounts"],
    queryFn: async () => {
      const res = await apiClient.get<CarrierAccount[]>("/logistics/carriers");
      return res.data;
    },
  });

  const { data: shipments, isLoading: shipmentsLoading } = useQuery({
    queryKey: ["shipments"],
    queryFn: async () => {
      const res = await apiClient.get<Shipment[]>("/logistics/shipments");
      return res.data;
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
      await apiClient.put(`/logistics/carriers/${id}`, { is_active });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["carrier-accounts"] }),
  });

  const cancelMutation = useMutation({
    mutationFn: async (id: string) => { await apiClient.post(`/logistics/shipments/${id}/cancel`); },
    onMutate: (id) => { setActionError(""); setCancellingId(id); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["shipments"] }),
    onError: (err: AxiosError<{ detail?: string }>) => setActionError(pickDetail(err, "تعذر إلغاء الشحنة.")),
    onSettled: () => setCancellingId(null),
  });

  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الشحن والتوصيل</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          اضبط شركات الشحن اللي بتتعامل معاها وتابع كل الشحنات في مكان واحد.
        </p>
      </div>

      {/* ── Carrier Accounts ─────────────────────────────────────────── */}
      <div className="glass-card rounded-xl p-card-padding space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-headline-sm text-headline-sm text-on-surface">شركات الشحن</h2>
          <button onClick={() => setModalOpen(true)} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-on-primary text-body-sm font-bold hover:opacity-90 transition-opacity">
            <Plus className="w-4 h-4" /> إضافة شركة شحن
          </button>
        </div>

        {accountsLoading ? (
          <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : !accounts || accounts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-on-surface-variant gap-2">
            <Truck className="w-8 h-8 text-outline-variant" />
            <p className="text-body-md">لسه معندكش شركات شحن مُعدّة.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {accounts.map((acc) => (
              <div key={acc.id} className="flex items-center justify-between p-3 rounded-lg bg-surface-container-low">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center"><Truck className="w-4 h-4" /></div>
                  <span className="font-semibold text-body-md text-on-surface">{carrierLabel[acc.carrier_code] ?? acc.carrier_code}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`px-2 py-1 rounded text-[11px] font-bold ${acc.is_active ? "bg-success-bg text-success" : "bg-surface-container text-on-surface-variant"}`}>
                    {acc.is_active ? "مُفعّل" : "غير مُفعّل"}
                  </span>
                  <button
                    onClick={() => toggleMutation.mutate({ id: acc.id, is_active: !acc.is_active })}
                    className="text-body-sm font-semibold text-primary hover:underline"
                  >
                    {acc.is_active ? "إيقاف" : "تفعيل"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Shipments ─────────────────────────────────────────────────── */}
      <div className="glass-card rounded-xl overflow-hidden">
        <div className="p-card-padding pb-0">
          <h2 className="font-headline-sm text-headline-sm text-on-surface mb-1">الشحنات</h2>
        </div>
        {actionError && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 mx-6 mt-3 rounded-lg text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {actionError}
          </div>
        )}
        {shipmentsLoading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : !shipments || shipments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <Package className="w-8 h-8 text-outline-variant" />
            <p className="text-body-md">لسه مفيش شحنات. أنشئ شحنة من صفحة المبيعات لفاتورة مرحّلة.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">رقم التتبع (AWB)</th>
                  <th className="px-6 py-4">شركة الشحن</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4">مبلغ التحصيل</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {shipments.map((s) => (
                  <tr key={s.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-data-mono" dir="ltr">
                      {s.tracking_url ? (
                        <a href={s.tracking_url} target="_blank" rel="noreferrer" className="text-primary hover:underline inline-flex items-center gap-1">
                          {s.awb_number} <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : s.awb_number}
                    </td>
                    <td className="px-6 py-4">{carrierLabel[s.carrier_code] ?? s.carrier_code}</td>
                    <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${stateTone[s.state]}`}>{stateLabel[s.state] ?? s.state}</span></td>
                    <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">{egp(s.cod_amount)}</td>
                    <td className="px-6 py-4">
                      {s.state !== "cancelled" && s.state !== "delivered" && s.state !== "returned" && (
                        <button
                          onClick={() => cancelMutation.mutate(s.id)}
                          disabled={cancellingId === s.id}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-error-container/20 text-error font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50 mr-auto"
                        >
                          {cancellingId === s.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Ban className="w-3.5 h-3.5" />} إلغاء
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
        <AddCarrierModal
          onClose={() => setModalOpen(false)}
          onCreated={() => { setModalOpen(false); queryClient.invalidateQueries({ queryKey: ["carrier-accounts"] }); }}
        />
      )}
    </div>
  );
}

interface CarrierForm {
  carrier_code: string;
  credentials_ref: string;
  webhook_secret_ref: string;
}

function AddCarrierModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [errorMsg, setErrorMsg] = useState("");
  const [showCreds, setShowCreds] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  const { data: available } = useQuery({
    queryKey: ["carriers-available"],
    queryFn: async () => {
      const res = await apiClient.get<AvailableCarrier[]>("/logistics/carriers/available");
      return res.data;
    },
  });

  const { register, handleSubmit, formState: { errors } } = useForm<CarrierForm>({
    defaultValues: { carrier_code: "", credentials_ref: "", webhook_secret_ref: "" },
  });

  const mutation = useMutation({
    mutationFn: async (data: CarrierForm) => {
      await apiClient.post("/logistics/carriers", { ...data, is_active: true });
    },
    onSuccess: onCreated,
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إضافة شركة الشحن.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">إضافة شركة شحن</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">شركة الشحن</label>
            <select {...register("carrier_code", { required: true })} className="input-field">
              <option value="">اختر شركة الشحن</option>
              {(available ?? []).map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
            </select>
            {errors.carrier_code && <p className="text-body-sm text-error">اختر شركة الشحن</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">مرجع بيانات الاعتماد (Credentials Ref)</label>
            <div className="relative">
              <input
                {...register("credentials_ref", { required: true })}
                dir="ltr"
                type={showCreds ? "text" : "password"}
                placeholder="vault://secrets/bosta/..."
                className="input-field font-mono pl-10"
              />
              <button type="button" onClick={() => setShowCreds((s) => !s)} className="absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors">
                {showCreds ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.credentials_ref && <p className="text-body-sm text-error">مطلوب</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">مرجع سر الويب هوك (Webhook Secret Ref)</label>
            <div className="relative">
              <input
                {...register("webhook_secret_ref", { required: true })}
                dir="ltr"
                type={showSecret ? "text" : "password"}
                placeholder="vault://secrets/bosta/webhook..."
                className="input-field font-mono pl-10"
              />
              <button type="button" onClick={() => setShowSecret((s) => !s)} className="absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors">
                {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.webhook_secret_ref && <p className="text-body-sm text-error">مطلوب</p>}
            <p className="text-body-sm text-outline">
              مراجع فقط — القيم الفعلية بتتخزن في الخزنة الآمنة (Vault) ولا تُحفظ أبدًا كنص صريح.
            </p>
          </div>

          <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} حفظ
          </button>
        </form>
      </div>
    </div>
  );
}
