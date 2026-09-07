"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { ReceiptText, Plus, Trash2, Loader2, AlertCircle, X, CheckCircle2, Landmark, Truck, ExternalLink, Wallet, Undo2, FileDown } from "lucide-react";

/**
 * The dedicated Sales page — didn't exist before. Ad-hoc invoicing used to
 * live inline inside the old Inventory page's "Invoices" tab (hitting the
 * now-retired app.plugins.inventory Invoice). This page wires the real
 * app.modules.sales ad-hoc path (POST /sales/invoices with contact_id+lines,
 * order_id left unset) — the flow service verticals like Hospitality and
 * Rental checkout will depend on for direct billing with no preceding
 * SalesOrder.
 */

type SalesInvoiceStatus = "DRAFT" | "POSTED" | "PAID" | "CANCELLED";

interface Item { id: string; sku: string; name: string; }
interface Contact { id: string; name: string; contact_type: "customer" | "supplier"; }

interface SalesInvoice {
  id: string;
  invoice_number: string;
  order_id: string | null;
  contact_id: string;
  status: SalesInvoiceStatus;
  issue_date: string;
  due_date: string;
  currency: string;
  subtotal: string | number;
  tax_total: string | number;
  grand_total: string | number;
}

type EtaDocumentState =
  | "DRAFT" | "READY" | "QUEUED" | "SIGNING" | "SIGNED" | "SUBMITTING" | "SUBMITTED"
  | "SUBMIT_FAILED" | "RATE_DEFERRED" | "SUBMIT_UNCERTAIN" | "ACCEPTED" | "REJECTED"
  | "INVALID" | "CANCELLED";

interface EtaDocument {
  id: string;
  state: EtaDocumentState;
  uuid: string | null;
  long_id: string | null;
}

const etaStateLabel: Record<EtaDocumentState, string> = {
  DRAFT: "مسودة", READY: "جاهزة", QUEUED: "في قائمة الانتظار", SIGNING: "جاري التوقيع",
  SIGNED: "موقّعة", SUBMITTING: "جاري الإرسال", SUBMITTED: "تم الإرسال",
  SUBMIT_FAILED: "فشل الإرسال", RATE_DEFERRED: "مؤجّلة (حد المعدل)",
  SUBMIT_UNCERTAIN: "غير مؤكدة — تحقق قبل إعادة الإرسال", ACCEPTED: "مقبولة من المصلحة",
  REJECTED: "مرفوضة من المصلحة", INVALID: "غير صالحة", CANCELLED: "ملغاة",
};
const etaStateTone: Record<EtaDocumentState, string> = {
  DRAFT: "bg-surface-container text-on-surface-variant",
  READY: "bg-primary-container/10 text-primary",
  QUEUED: "bg-primary-container/10 text-primary",
  SIGNING: "bg-warning-bg text-warning",
  SIGNED: "bg-primary-container/10 text-primary",
  SUBMITTING: "bg-warning-bg text-warning",
  SUBMITTED: "bg-success-bg text-success",
  SUBMIT_FAILED: "bg-error-container text-on-error-container",
  RATE_DEFERRED: "bg-warning-bg text-warning",
  SUBMIT_UNCERTAIN: "bg-warning-bg text-warning",
  ACCEPTED: "bg-success-bg text-success",
  REJECTED: "bg-error-container text-on-error-container",
  INVALID: "bg-error-container text-on-error-container",
  CANCELLED: "bg-surface-container text-on-surface-variant",
};

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const statusLabel: Record<SalesInvoiceStatus, string> = { DRAFT: "مسودة", POSTED: "مرحّلة", PAID: "مدفوعة", CANCELLED: "ملغاة" };
const statusTone: Record<SalesInvoiceStatus, string> = {
  DRAFT: "bg-primary-container/10 text-primary",
  POSTED: "bg-success-bg text-success",
  PAID: "bg-success-bg text-success",
  CANCELLED: "bg-error-container text-on-error-container",
};

interface SalesInvoiceLine {
  id: string;
  item_id: string;
  variant_id: string | null;
  uom_id: string | null;
  qty: string | number;
  unit_price: string | number;
  line_total: string | number;
  tax_rate: string | number;
  tax_amount: string | number;
}
interface SalesInvoiceDetail extends SalesInvoice {
  lines: SalesInvoiceLine[];
}
interface Warehouse { id: string; code: string; name: string; }

interface Shipment {
  id: string;
  invoice_id: string;
  carrier_code: string;
  awb_number: string;
  tracking_url: string | null;
  state: string;
}
interface AvailableCarrier { code: string; label: string; }

const shipmentStateLabel: Record<string, string> = {
  created: "تم الإنشاء", picked_up: "تم الاستلام", in_transit: "في الطريق",
  out_for_delivery: "خارج للتسليم", delivered: "تم التسليم", returning: "عائدة",
  returned: "تم الإرجاع", lost: "مفقودة", cancelled: "ملغاة",
};
const shipmentStateTone: Record<string, string> = {
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

export default function SalesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [actionError, setActionError] = useState("");
  const [postingId, setPostingId] = useState<string | null>(null);

  const { data: invoices, isLoading, isError } = useQuery({
    queryKey: ["sales-invoices"],
    queryFn: async () => {
      const res = await apiClient.get<SalesInvoice[]>("/sales/invoices");
      return res.data;
    },
  });

  const { data: contacts } = useQuery({
    queryKey: ["contacts", "for-sales"],
    queryFn: async () => {
      const res = await apiClient.get<{ items: Contact[] }>("/contacts", { params: { limit: 200 } });
      return res.data.items;
    },
  });
  const customers = (contacts ?? []).filter((c) => c.contact_type === "customer");
  const contactsById = new Map((contacts ?? []).map((c) => [c.id, c]));

  const { data: items } = useQuery({
    queryKey: ["inventory-items", "for-sales"],
    queryFn: async () => {
      const res = await apiClient.get<Item[]>("/inventory/items");
      return res.data;
    },
  });

  const postMutation = useMutation({
    mutationFn: async (id: string) => { await apiClient.post(`/sales/invoices/${id}/post`); },
    onMutate: (id) => { setActionError(""); setPostingId(id); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales-invoices"] }),
    onError: (err: AxiosError<{ detail?: string }>) => setActionError(pickDetail(err, "تعذر ترحيل الفاتورة.")),
    onSettled: () => setPostingId(null),
  });

  const [etaResults, setEtaResults] = useState<Record<string, EtaDocument>>({});
  const [etaSubmittingId, setEtaSubmittingId] = useState<string | null>(null);
  const [etaError, setEtaError] = useState("");

  const { data: shipments } = useQuery({
    queryKey: ["shipments", "for-sales"],
    queryFn: async () => {
      const res = await apiClient.get<Shipment[]>("/logistics/shipments");
      return res.data;
    },
  });
  const shipmentByInvoiceId = new Map((shipments ?? []).map((s) => [s.invoice_id, s]));
  const [shipInvoiceId, setShipInvoiceId] = useState<string | null>(null);
  // Guards against the modal crashing: `invoices` can still be undefined
  // (loading/error) or the id can point at an invoice no longer in the
  // list (e.g. a stale click right as the query refetches) — in both
  // cases this resolves to undefined and the modal simply doesn't render
  // instead of throwing on a non-null assertion.
  const shipInvoice = invoices?.find((i) => i.id === shipInvoiceId);

  const [payInvoiceId, setPayInvoiceId] = useState<string | null>(null);
  const payInvoice = invoices?.find((i) => i.id === payInvoiceId);
  const [returnInvoiceId, setReturnInvoiceId] = useState<string | null>(null);
  const returnInvoice = invoices?.find((i) => i.id === returnInvoiceId);

  const submitEtaMutation = useMutation({
    mutationFn: async (invoiceId: string) => {
      const res = await apiClient.post<EtaDocument>(`/eta/submissions/invoice/${invoiceId}`);
      return { invoiceId, doc: res.data };
    },
    onMutate: (invoiceId) => { setEtaError(""); setEtaSubmittingId(invoiceId); },
    onSuccess: ({ invoiceId, doc }) => {
      setEtaResults((prev) => ({ ...prev, [invoiceId]: doc }));
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setEtaError(pickDetail(err, "تعذر إرسال الفاتورة لمنظومة الفاتورة الإلكترونية."));
    },
    onSettled: () => setEtaSubmittingId(null),
  });

  // PDF download — mirrors the cases module's itinerary.pdf download
  // pattern (blob response, synthetic <a download> click). Available
  // regardless of invoice status (draft invoices can be previewed too).
  const [pdfDownloadingId, setPdfDownloadingId] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState("");
  const pdfMutation = useMutation({
    mutationFn: async (invoice: SalesInvoice) => {
      const res = await apiClient.get(`/sales/invoices/${invoice.id}/pdf`, { responseType: "blob" });
      return { invoice, blob: res.data as Blob };
    },
    onMutate: (invoice) => { setPdfError(""); setPdfDownloadingId(invoice.id); },
    onSuccess: ({ invoice, blob }) => {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `invoice-${invoice.invoice_number}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
    onError: (err: AxiosError<{ detail?: string }>) => setPdfError(pickDetail(err, "تعذر تحميل ملف PDF للفاتورة.")),
    onSettled: () => setPdfDownloadingId(null),
  });

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">المبيعات</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            فواتير مباشرة لعملائك — الترحيل يُنشئ قيد محاسبي تلقائيًا.
          </p>
        </div>
        <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
          <Plus className="w-4 h-4" /> فاتورة مبيعات جديدة
        </button>
      </div>

      {actionError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {actionError}
        </div>
      )}
      {etaError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {etaError}
        </div>
      )}
      {pdfError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {pdfError}
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error"><AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل فواتير المبيعات.</div>
        ) : !invoices || invoices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <ReceiptText className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد فواتير مبيعات بعد.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">رقم الفاتورة</th>
                  <th className="px-6 py-4">العميل</th>
                  <th className="px-6 py-4">النوع</th>
                  <th className="px-6 py-4">تاريخ الإصدار</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4">الفاتورة الإلكترونية</th>
                  <th className="px-6 py-4">الشحن</th>
                  <th className="px-6 py-4">الإجمالي</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {invoices.map((inv) => {
                  const busy = postingId === inv.id;
                  const etaBusy = etaSubmittingId === inv.id;
                  const etaDoc = etaResults[inv.id];
                  return (
                    <tr key={inv.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{inv.invoice_number}</td>
                      <td className="px-6 py-4 font-medium">{contactsById.get(inv.contact_id)?.name ?? "—"}</td>
                      <td className="px-6 py-4 text-body-sm text-on-surface-variant">{inv.order_id ? "من أمر بيع" : "مباشرة"}</td>
                      <td className="px-6 py-4 text-outline font-data-mono" dir="ltr">{new Date(inv.issue_date).toLocaleDateString("en-GB")}</td>
                      <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[inv.status]}`}>{statusLabel[inv.status]}</span></td>
                      <td className="px-6 py-4">
                        {etaDoc ? (
                          <span className={`px-2 py-1 rounded text-[11px] font-bold ${etaStateTone[etaDoc.state]}`}>{etaStateLabel[etaDoc.state]}</span>
                        ) : (
                          <span className="text-body-sm text-outline">—</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {(() => {
                          const shipment = shipmentByInvoiceId.get(inv.id);
                          if (shipment) {
                            return (
                              <div className="flex items-center gap-2">
                                <span className={`px-2 py-1 rounded text-[11px] font-bold ${shipmentStateTone[shipment.state] ?? "bg-surface-container text-on-surface-variant"}`}>
                                  {shipmentStateLabel[shipment.state] ?? shipment.state}
                                </span>
                                {shipment.tracking_url ? (
                                  <a href={shipment.tracking_url} target="_blank" rel="noreferrer" dir="ltr" className="font-data-mono text-body-sm text-primary hover:underline inline-flex items-center gap-1">
                                    {shipment.awb_number} <ExternalLink className="w-3 h-3" />
                                  </a>
                                ) : (
                                  <span dir="ltr" className="font-data-mono text-body-sm text-on-surface-variant">{shipment.awb_number}</span>
                                )}
                              </div>
                            );
                          }
                          if (inv.status === "POSTED" || inv.status === "PAID") {
                            return (
                              <button
                                onClick={() => setShipInvoiceId(inv.id)}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-tertiary-container/20 text-tertiary font-semibold text-body-sm hover:opacity-80 transition-opacity"
                              >
                                <Truck className="w-3.5 h-3.5" /> شحن
                              </button>
                            );
                          }
                          return <span className="text-body-sm text-outline">—</span>;
                        })()}
                      </td>
                      <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">{egp(inv.grand_total)}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2 justify-end">
                          <button
                            onClick={() => pdfMutation.mutate(inv)}
                            disabled={pdfDownloadingId === inv.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-container text-on-surface-variant font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50"
                          >
                            {pdfDownloadingId === inv.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />} PDF
                          </button>
                          {inv.status === "DRAFT" && (
                            <button onClick={() => postMutation.mutate(inv.id)} disabled={busy} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success-bg text-success font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50">
                              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />} ترحيل
                            </button>
                          )}
                          {inv.status === "POSTED" && !etaDoc && (
                            <button
                              onClick={() => submitEtaMutation.mutate(inv.id)}
                              disabled={etaBusy}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-tertiary-container/20 text-tertiary font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50"
                            >
                              {etaBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Landmark className="w-3.5 h-3.5" />} إرسال للضرائب
                            </button>
                          )}
                          {inv.status === "POSTED" && etaDoc && etaDoc.state === "SUBMIT_UNCERTAIN" && (
                            <button
                              onClick={() => submitEtaMutation.mutate(inv.id)}
                              disabled={etaBusy}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-tertiary-container/20 text-tertiary font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50"
                            >
                              {etaBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Landmark className="w-3.5 h-3.5" />} إعادة المحاولة
                            </button>
                          )}
                          {inv.status === "POSTED" && (
                            <button
                              onClick={() => setPayInvoiceId(inv.id)}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success-bg text-success font-semibold text-body-sm hover:opacity-80 transition-opacity"
                            >
                              <Wallet className="w-3.5 h-3.5" /> تحصيل دفعة
                            </button>
                          )}
                          {(inv.status === "POSTED" || inv.status === "PAID") && (
                            <button
                              onClick={() => setReturnInvoiceId(inv.id)}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-warning-bg text-warning font-semibold text-body-sm hover:opacity-80 transition-opacity"
                            >
                              <Undo2 className="w-3.5 h-3.5" /> مرتجع
                            </button>
                          )}
                        </div>
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
        <CreateInvoiceModal
          customers={customers}
          items={items ?? []}
          onClose={() => setModalOpen(false)}
          onCreated={() => { setModalOpen(false); queryClient.invalidateQueries({ queryKey: ["sales-invoices"] }); }}
        />
      )}

      {shipInvoiceId && shipInvoice && (
        <ShipInvoiceModal
          invoice={shipInvoice}
          onClose={() => setShipInvoiceId(null)}
          onShipped={() => {
            setShipInvoiceId(null);
            queryClient.invalidateQueries({ queryKey: ["shipments", "for-sales"] });
          }}
        />
      )}

      {payInvoiceId && payInvoice && (
        <PayInvoiceModal
          invoice={payInvoice}
          onClose={() => setPayInvoiceId(null)}
          onPaid={() => {
            setPayInvoiceId(null);
            queryClient.invalidateQueries({ queryKey: ["sales-invoices"] });
          }}
        />
      )}

      {returnInvoiceId && returnInvoice && (
        <ReturnInvoiceModal
          invoice={returnInvoice}
          onClose={() => setReturnInvoiceId(null)}
          onReturned={() => {
            setReturnInvoiceId(null);
            queryClient.invalidateQueries({ queryKey: ["sales-invoices"] });
          }}
        />
      )}
    </div>
  );
}

function ShipInvoiceModal({
  invoice,
  onClose,
  onShipped,
}: {
  invoice: SalesInvoice;
  onClose: () => void;
  onShipped: () => void;
}) {
  const [errorMsg, setErrorMsg] = useState("");
  const [carrierCode, setCarrierCode] = useState("");
  const [codAmount, setCodAmount] = useState<string>(String(invoice.grand_total));
  const [dropoffAddress, setDropoffAddress] = useState("");

  const { data: accounts, isLoading: accountsLoading } = useQuery({
    queryKey: ["carrier-accounts", "for-ship-modal"],
    queryFn: async () => {
      const res = await apiClient.get<{ id: string; carrier_code: string; is_active: boolean }[]>("/logistics/carriers");
      return res.data.filter((a) => a.is_active);
    },
  });

  const mutation = useMutation({
    mutationFn: async () => {
      await apiClient.post("/logistics/shipments", {
        invoice_id: invoice.id,
        carrier_code: carrierCode,
        cod_amount: Number(codAmount) || 0,
        dropoff_address: dropoffAddress || undefined,
      });
    },
    onSuccess: onShipped,
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إنشاء الشحنة.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">شحن الفاتورة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-body-sm text-on-surface-variant mb-4">
          فاتورة <span dir="ltr" className="font-data-mono">{invoice.invoice_number}</span> — {egp(invoice.grand_total)}
        </p>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        {accountsLoading ? (
          <div className="flex items-center justify-center py-8 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : !accounts || accounts.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">
            لازم تضبط شركة شحن مُفعّلة أولًا من صفحة{" "}
            <a href="/dashboard/shipping" className="text-primary hover:underline">الشحن والتوصيل</a>.
          </p>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">شركة الشحن</label>
              <select value={carrierCode} onChange={(e) => setCarrierCode(e.target.value)} required className="input-field">
                <option value="">اختر شركة الشحن</option>
                {accounts.map((a) => <option key={a.id} value={a.carrier_code}>{a.carrier_code}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">مبلغ التحصيل عند الاستلام (COD)</label>
              <input type="number" step="0.01" dir="ltr" value={codAmount} onChange={(e) => setCodAmount(e.target.value)} className="input-field font-mono" />
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">عنوان التسليم (اختياري)</label>
              <input type="text" value={dropoffAddress} onChange={(e) => setDropoffAddress(e.target.value)} className="input-field" placeholder="العنوان بالتفصيل" />
            </div>
            <button type="submit" disabled={mutation.isPending || !carrierCode} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
              {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Truck className="w-4 h-4" />} إنشاء الشحنة
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

function PayInvoiceModal({
  invoice,
  onClose,
  onPaid,
}: {
  invoice: SalesInvoice;
  onClose: () => void;
  onPaid: () => void;
}) {
  const [errorMsg, setErrorMsg] = useState("");
  const [amount, setAmount] = useState<string>(String(invoice.grand_total));
  const [paymentMethod, setPaymentMethod] = useState("CASH");
  const [reference, setReference] = useState("");

  // Full lifecycle in one submit: create the DRAFT payment, allocate it
  // against this invoice, then post it — mirrors exactly what was verified
  // live against the real API (create -> allocate -> post), just collapsed
  // into a single user action since this modal only ever pays one invoice
  // in full or in part, never splits across several.
  const mutation = useMutation({
    mutationFn: async () => {
      const paymentNumber = `PAY-${invoice.invoice_number}-${Date.now().toString(36).toUpperCase()}`;
      const created = await apiClient.post<{ id: string }>("/sales/payments", {
        contact_id: invoice.contact_id,
        payment_number: paymentNumber,
        amount,
        payment_method: paymentMethod,
        reference: reference || undefined,
        currency: invoice.currency,
      });
      const paymentId = created.data.id;
      await apiClient.post(`/sales/payments/${paymentId}/allocate`, {
        invoice_id: invoice.id,
        allocated_amount: amount,
      });
      await apiClient.post(`/sales/payments/${paymentId}/post`);
    },
    onSuccess: onPaid,
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر تسجيل الدفعة.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">تحصيل دفعة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-body-sm text-on-surface-variant mb-4">
          فاتورة <span dir="ltr" className="font-data-mono">{invoice.invoice_number}</span> — إجمالي {egp(invoice.grand_total)}
        </p>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">المبلغ المحصّل</label>
            <input type="number" step="0.01" dir="ltr" value={amount} onChange={(e) => setAmount(e.target.value)} required className="input-field font-mono" />
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">طريقة الدفع</label>
            <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} className="input-field">
              <option value="CASH">نقدًا</option>
              <option value="BANK_TRANSFER">تحويل بنكي</option>
              <option value="CARD">بطاقة</option>
              <option value="CHEQUE">شيك</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">مرجع (اختياري)</label>
            <input type="text" value={reference} onChange={(e) => setReference(e.target.value)} className="input-field" placeholder="رقم إيصال، رقم تحويل..." />
          </div>
          <button type="submit" disabled={mutation.isPending || !amount || Number(amount) <= 0} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wallet className="w-4 h-4" />} تسجيل وترحيل الدفعة
          </button>
        </form>
      </div>
    </div>
  );
}

function ReturnInvoiceModal({
  invoice,
  onClose,
  onReturned,
}: {
  invoice: SalesInvoice;
  onClose: () => void;
  onReturned: () => void;
}) {
  const [errorMsg, setErrorMsg] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  // lineId -> qty to return (string input, empty = not returning this line)
  const [returnQty, setReturnQty] = useState<Record<string, string>>({});

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["sales-invoice-detail", invoice.id],
    queryFn: async () => {
      const res = await apiClient.get<SalesInvoiceDetail>(`/sales/invoices/${invoice.id}`);
      return res.data;
    },
  });

  const { data: warehouses } = useQuery({
    queryKey: ["warehouses", "for-returns"],
    queryFn: async () => {
      const res = await apiClient.get<Warehouse[]>("/inventory/warehouses");
      return res.data;
    },
  });

  const selectedLines = (detail?.lines ?? []).filter((l) => Number(returnQty[l.id]) > 0);

  const mutation = useMutation({
    mutationFn: async () => {
      const lines = selectedLines.map((l) => ({
        original_invoice_line_id: l.id,
        item_id: l.item_id,
        variant_id: l.variant_id ?? undefined,
        uom_id: l.uom_id ?? undefined,
        qty: returnQty[l.id],
        unit_price: l.unit_price,
        tax_rate: l.tax_rate,
      }));
      const created = await apiClient.post<{ id: string }>("/sales/returns", {
        invoice_id: invoice.id,
        contact_id: invoice.contact_id,
        lines,
      });
      const returnId = created.data.id;
      await apiClient.post(`/sales/returns/${returnId}/process`, { warehouse_id: warehouseId });
      await apiClient.post(`/sales/returns/${returnId}/credit-note`);
    },
    onSuccess: onReturned,
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر تسجيل المرتجع.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">مرتجع مبيعات</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-body-sm text-on-surface-variant mb-4">
          فاتورة <span dir="ltr" className="font-data-mono">{invoice.invoice_number}</span> — سيتم إصدار إشعار دائن (Credit Note) بقيمة الأصناف المرتجعة.
        </p>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        {detailLoading ? (
          <div className="flex items-center justify-center py-8 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : !detail || detail.lines.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">لا توجد أصناف في هذه الفاتورة.</p>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">المخزن المستلم للمرتجع</label>
              <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)} required className="input-field">
                <option value="">اختر المخزن</option>
                {(warehouses ?? []).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </div>
            <div className="space-y-3">
              <label className="text-body-sm font-semibold text-on-surface-variant">الأصناف المرتجعة (اترك الكمية فارغة لعدم إرجاع الصنف)</label>
              {detail.lines.map((l) => (
                <div key={l.id} className="flex items-center gap-2">
                  <span className="flex-1 text-body-sm font-data-mono" dir="ltr">
                    {l.item_id.slice(0, 8)}… × {l.qty} @ {egp(l.unit_price)}
                  </span>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    max={String(l.qty)}
                    dir="ltr"
                    placeholder="0"
                    value={returnQty[l.id] ?? ""}
                    onChange={(e) => setReturnQty((prev) => ({ ...prev, [l.id]: e.target.value }))}
                    className="input-field w-24 font-mono"
                  />
                </div>
              ))}
            </div>
            <button
              type="submit"
              disabled={mutation.isPending || !warehouseId || selectedLines.length === 0}
              className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
            >
              {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Undo2 className="w-4 h-4" />} تسجيل المرتجع وإصدار إشعار دائن
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

const lineSchema = z.object({
  item_id: z.string().min(1, "اختر الصنف"),
  qty: z.coerce.number().gt(0, "الكمية أكبر من صفر"),
  unit_price: z.coerce.number().min(0, "السعر لازم يكون رقم موجب"),
});
const schema = z.object({
  contact_id: z.string().min(1, "اختر العميل"),
  lines: z.array(lineSchema).min(1),
});
type FormOut = z.output<typeof schema>;
type FormIn = z.input<typeof schema>;

function CreateInvoiceModal({
  customers,
  items,
  onClose,
  onCreated,
}: {
  customers: Contact[];
  items: Item[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [errorMsg, setErrorMsg] = useState("");
  const { register, control, handleSubmit, formState: { errors } } = useForm<FormIn, any, FormOut>({
    resolver: zodResolver(schema),
    defaultValues: { contact_id: "", lines: [{ item_id: "", qty: 1, unit_price: 0 }] },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "lines" });

  // Generated once per modal mount and sent as the Idempotency-Key header —
  // defense-in-depth alongside the submit button's disabled-while-pending
  // state below: if the same key is replayed (e.g. a network retry re-sends
  // this exact request), the backend (app.core.idempotency) returns the
  // invoice already created by the first attempt instead of a duplicate.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  const mutation = useMutation({
    mutationFn: async (data: FormOut) => {
      // Ad-hoc path: contact_id + lines, order_id intentionally omitted so
      // the backend routes this to create_adhoc_invoice() instead of
      // generate_invoice_from_order().
      await apiClient.post(
        "/sales/invoices",
        {
          contact_id: data.contact_id,
          lines: data.lines.map((l) => ({ item_id: l.item_id, qty: l.qty, unit_price: l.unit_price })),
        },
        { headers: { "Idempotency-Key": idempotencyKey } },
      );
    },
    onSuccess: onCreated,
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إنشاء الفاتورة.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">فاتورة مبيعات جديدة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        {customers.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">أضف عميل واحد على الأقل (من جهات الاتصال) قبل إنشاء فاتورة.</p>
        ) : items.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">أضف صنف واحد على الأقل (من صفحة المخزون) قبل إنشاء فاتورة.</p>
        ) : (
          <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">العميل</label>
              <select {...register("contact_id")} className="input-field">
                <option value="">اختر العميل</option>
                {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              {errors.contact_id && <p className="text-body-sm text-error">{errors.contact_id.message}</p>}
            </div>

            <div className="space-y-3">
              <label className="text-body-sm font-semibold text-on-surface-variant">الأصناف</label>
              {fields.map((field, idx) => (
                <div key={field.id} className="flex gap-2 items-start">
                  <select {...register(`lines.${idx}.item_id` as const)} className="input-field flex-1">
                    <option value="">اختر الصنف</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>{it.name} ({it.sku})</option>
                    ))}
                  </select>
                  <input type="number" step="1" placeholder="الكمية" dir="ltr" {...register(`lines.${idx}.qty` as const)} className="input-field w-20 font-mono" />
                  <input type="number" step="0.01" placeholder="السعر" dir="ltr" {...register(`lines.${idx}.unit_price` as const)} className="input-field w-24 font-mono" />
                  <button type="button" onClick={() => remove(idx)} className="p-2.5 text-error hover:bg-error-container/20 rounded-lg transition-colors shrink-0"><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
              {errors.lines?.message && <p className="text-body-sm text-error">{errors.lines.message}</p>}
              <button type="button" onClick={() => append({ item_id: "", qty: 1, unit_price: 0 })} className="flex items-center gap-1 text-primary font-semibold text-body-sm hover:underline">
                <Plus className="w-4 h-4" /> إضافة صنف
              </button>
            </div>

            <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
              {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الفاتورة
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
