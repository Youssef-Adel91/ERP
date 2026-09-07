"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ChevronDown, ExternalLink, FileText } from "lucide-react";
import { portalApiClient, getPortalToken } from "@/lib/portal-api-client";
import { pickDetail } from "@/lib/api-client";
import { PortalHeader } from "@/components/portal/PortalHeader";

interface InvoiceLine {
  id: string;
  item_id: string;
  qty: string;
  unit_price: string;
  line_total: string;
  tax_amount: string;
}

interface Invoice {
  id: string;
  invoice_number: string;
  status: "DRAFT" | "POSTED" | "PAID" | "CANCELLED";
  issue_date: string;
  due_date: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  grand_total: string;
  // GET /portal/invoices returns bare SalesInvoice rows with no
  // response_model — FastAPI's default serialization only walks actual
  // Pydantic/table fields, not the `lines` SQLAlchemy Relationship, so
  // this key is absent from the real response even though the backend
  // model declares it. Treated as optional/possibly-missing everywhere
  // it's used below (confirmed live: a real response has no "lines" key
  // at all, not even an empty array).
  lines?: InvoiceLine[];
}

interface PaymentIntent {
  intent_id: string;
  checkout_url: string;
  amount: number;
  currency: string;
}

function formatMoney(value: string, currency: string) {
  const n = Number(value);
  return `${n.toLocaleString("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatDate(value: string) {
  try {
    return new Date(value).toLocaleDateString("ar-EG", { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return value;
  }
}

export default function PortalInvoicesPage() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [payingId, setPayingId] = useState<string | null>(null);
  const [payResult, setPayResult] = useState<Record<string, PaymentIntent>>({});
  const [payError, setPayError] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!getPortalToken()) {
      router.replace("/portal/login");
      return;
    }
    loadInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadInvoices() {
    setErrorMsg("");
    try {
      const { data } = await portalApiClient.get<Invoice[]>("/portal/invoices");
      setInvoices(data);
    } catch (err) {
      setErrorMsg(pickDetail(err, "تعذر تحميل الفواتير، حاول مرة أخرى."));
      setInvoices([]);
    }
  }

  async function handlePay(invoiceId: string) {
    setPayingId(invoiceId);
    setPayError((prev) => ({ ...prev, [invoiceId]: "" }));
    try {
      const { data } = await portalApiClient.post<PaymentIntent>(`/portal/invoices/${invoiceId}/pay`);
      setPayResult((prev) => ({ ...prev, [invoiceId]: data }));
      window.open(data.checkout_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setPayError((prev) => ({
        ...prev,
        [invoiceId]: pickDetail(err, "تعذر بدء عملية الدفع، حاول مرة أخرى."),
      }));
    } finally {
      setPayingId(null);
    }
  }

  return (
    <div className="min-h-screen bg-surface">
      <PortalHeader />
      <main className="max-w-3xl mx-auto px-gutter py-8">
        <div className="mb-6">
          <h2 className="font-headline-sm text-headline-sm text-on-surface mb-1">فواتيرك المستحقة</h2>
          <p className="text-body-sm text-on-surface-variant">
            يعرض هذا القسم الفواتير الصادرة وغير المسددة بعد. للفواتير المدفوعة راجع سجلاتك السابقة.
          </p>
        </div>

        {errorMsg && (
          <div className="w-full flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {errorMsg}
          </div>
        )}

        {invoices === null && (
          <div className="glass-card rounded-xl p-10 text-center text-on-surface-variant">جاري التحميل...</div>
        )}

        {invoices !== null && invoices.length === 0 && !errorMsg && (
          <div className="glass-card rounded-xl p-10 text-center">
            <FileText className="w-10 h-10 mx-auto mb-3 text-on-surface-variant" />
            <p className="text-body-md text-on-surface-variant">لا توجد فواتير مستحقة عليك حالياً.</p>
          </div>
        )}

        <div className="space-y-4">
          {invoices?.map((inv) => {
            const isExpanded = expandedId === inv.id;
            const intent = payResult[inv.id];
            return (
              <div key={inv.id} className="glass-card rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setExpandedId(isExpanded ? null : inv.id)}
                  className="w-full flex items-center justify-between p-5 text-right hover:bg-surface-container-low transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-primary-fixed flex items-center justify-center shrink-0">
                      <FileText className="w-5 h-5 text-on-primary-fixed" />
                    </div>
                    <div>
                      <p className="font-headline-sm text-headline-sm text-on-surface">{inv.invoice_number}</p>
                      <p className="text-body-sm text-on-surface-variant">
                        تاريخ الاستحقاق: {formatDate(inv.due_date)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-headline-sm text-headline-sm text-primary">
                      {formatMoney(inv.grand_total, inv.currency)}
                    </span>
                    <ChevronDown
                      className={`w-5 h-5 text-on-surface-variant transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    />
                  </div>
                </button>

                {isExpanded && (
                  <div className="border-t border-outline-variant p-5 bg-surface-container-low space-y-4">
                    <div className="grid grid-cols-2 gap-4 text-body-sm">
                      <div>
                        <p className="text-on-surface-variant">تاريخ الإصدار</p>
                        <p className="text-on-surface font-medium">{formatDate(inv.issue_date)}</p>
                      </div>
                      <div>
                        <p className="text-on-surface-variant">الإجمالي قبل الضريبة</p>
                        <p className="text-on-surface font-medium">{formatMoney(inv.subtotal, inv.currency)}</p>
                      </div>
                      <div>
                        <p className="text-on-surface-variant">الضريبة</p>
                        <p className="text-on-surface font-medium">{formatMoney(inv.tax_total, inv.currency)}</p>
                      </div>
                      <div>
                        <p className="text-on-surface-variant">الإجمالي المستحق</p>
                        <p className="text-on-surface font-bold">{formatMoney(inv.grand_total, inv.currency)}</p>
                      </div>
                    </div>

                    {inv.lines && inv.lines.length > 0 && (
                      <div className="overflow-x-auto">
                        <table className="w-full text-body-sm">
                          <thead>
                            <tr className="text-on-surface-variant border-b border-outline-variant">
                              <th className="text-right py-2 font-medium">الكمية</th>
                              <th className="text-right py-2 font-medium">سعر الوحدة</th>
                              <th className="text-right py-2 font-medium">الإجمالي</th>
                            </tr>
                          </thead>
                          <tbody>
                            {inv.lines.map((line) => (
                              <tr key={line.id} className="border-b border-outline-variant/50 last:border-0">
                                <td className="py-2 text-on-surface">{line.qty}</td>
                                <td className="py-2 text-on-surface">{formatMoney(line.unit_price, inv.currency)}</td>
                                <td className="py-2 text-on-surface font-medium">
                                  {formatMoney(line.line_total, inv.currency)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {payError[inv.id] && (
                      <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        {payError[inv.id]}
                      </div>
                    )}

                    {intent && (
                      <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg text-body-sm font-medium border border-success/30">
                        <CheckCircleIcon />
                        <span>
                          تم فتح رابط الدفع في نافذة جديدة.{" "}
                          <a
                            href={intent.checkout_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline"
                          >
                            افتحه مرة أخرى
                          </a>
                        </span>
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => handlePay(inv.id)}
                      disabled={payingId === inv.id}
                      className="w-full sm:w-auto bg-primary text-on-primary py-3 px-6 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-container hover:shadow-overlay active:scale-[0.98] transition-all duration-200 disabled:opacity-70"
                    >
                      {payingId === inv.id ? (
                        <>
                          <svg className="w-4 h-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          <span>جاري التجهيز...</span>
                        </>
                      ) : (
                        <>
                          <span>دفع الفاتورة</span>
                          <ExternalLink className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}

function CheckCircleIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-4 h-4 fill-current shrink-0">
      <path d="m424-296 282-282-56-56-226 226-114-114-56 56 170 170Zm56 216q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Z" />
    </svg>
  );
}
