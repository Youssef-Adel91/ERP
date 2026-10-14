"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  ArrowRight,
  Loader2,
  AlertCircle,
  Stamp,
  Calendar,
  ChevronLeft,
  Plus,
  X,
  Paperclip,
  Upload,
  Download,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface Booking {
  id: string;
  title: string | null;
  data: Record<string, any>;
}

interface Visa {
  id: string;
  case_id: string;
  passenger_name: string;
  passport_number: string | null;
  destination_country: string;
  visa_type: string;
  status: string;
  is_active: boolean;
  vendor_name: string | null;
  submitted_date: string | null;
  expected_decision_date: string | null;
  decision_date: string | null;
  cost: number;
  fee_charged: number;
  currency: string;
  booking_title: string | null;
}

interface VisaDocument {
  id: string;
  visa_id: string;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  uploaded_by: string | null;
}

const STATUS_FLOW = [
  "not_started",
  "documents_collected",
  "submitted",
  "interview_scheduled",
  "approved",
  "received",
];

const STATUS_LABEL: Record<string, string> = {
  not_started: "لم يبدأ",
  documents_collected: "المستندات جاهزة",
  submitted: "تم التقديم",
  interview_scheduled: "مقابلة محددة",
  approved: "موافق عليها",
  rejected: "مرفوضة",
  received: "تم الاستلام",
};

const STATUS_TONE: Record<string, BadgeTone> = {
  not_started: "neutral",
  documents_collected: "primary",
  submitted: "primary",
  interview_scheduled: "tertiary",
  approved: "secondary",
  rejected: "error",
  received: "success",
};

const ALLOWED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/gif",
  "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
const MAX_SIZE_BYTES = 5 * 1024 * 1024;

const egp = (v: number, currency = "EGP") =>
  `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ${currency === "EGP" ? "ج.م" : currency}`;

const fmtSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export default function TravelVisasPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [expandedVisaId, setExpandedVisaId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadingVisaId, setUploadingVisaId] = useState<string | null>(null);

  // Tracks which visa row currently has an in-flight status transition.
  const [transitioningId, setTransitioningId] = useState<string | null>(null);
  const [form, setForm] = useState({
    case_id: "",
    passenger_name: "",
    passport_number: "",
    destination_country: "",
    visa_type: "tourist",
    fee_charged: 0,
    cost: 0,
  });

  const { data: visas, isLoading, isError } = useQuery({
    queryKey: ["travel-visas", statusFilter, includeArchived],
    queryFn: async () => {
      const res = await apiClient.get<Visa[]>("/travel/visas", {
        params: {
          ...(statusFilter ? { status_filter: statusFilter } : {}),
          ...(includeArchived ? { include_archived: true } : {}),
        },
      });
      return res.data;
    },
  });

  const { data: caseTypes } = useQuery({
    queryKey: ["case-types", "travel"],
    enabled: showAdd,
    queryFn: async () => {
      const res = await apiClient.get<{ id: string; code: string }[]>("/case-types", { params: { plugin_key: "travel" } });
      return res.data;
    },
  });
  const caseType = caseTypes?.find((c) => c.code === "travel_booking");

  const { data: bookings } = useQuery({
    queryKey: ["travel-bookings-for-visa", caseType?.id],
    enabled: showAdd && !!caseType,
    queryFn: async () => {
      const res = await apiClient.get<Booking[]>("/cases", { params: { case_type_id: caseType!.id } });
      return res.data;
    },
  });

  // ── Documents query (loaded when a row is expanded) ───────────────────────
  const { data: docsForVisa, isLoading: docsLoading } = useQuery({
    queryKey: ["visa-documents", expandedVisaId],
    enabled: !!expandedVisaId,
    queryFn: async () => {
      const res = await apiClient.get<VisaDocument[]>(`/travel/visas/${expandedVisaId}/documents`);
      return res.data;
    },
  });

  const transitionMutation = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) => {
      await apiClient.post(`/travel/visas/${id}/transition`, { status });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["travel-visas"] }),
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر تحديث حالة التأشيرة.")),
    onSettled: () => setTransitioningId(null),
  });

  const requestTransition = (id: string, status: string) => {
    if (transitioningId) return;
    setTransitioningId(id);
    setErrorMsg("");
    transitionMutation.mutate({ id, status });
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/travel/cases/${form.case_id}/visas`, {
        passenger_name: form.passenger_name,
        passport_number: form.passport_number || undefined,
        destination_country: form.destination_country,
        visa_type: form.visa_type,
        fee_charged: form.fee_charged,
        cost: form.cost,
      });
    },
    onSuccess: () => {
      setShowAdd(false);
      setForm({ case_id: "", passenger_name: "", passport_number: "", destination_country: "", visa_type: "tourist", fee_charged: 0, cost: 0 });
      queryClient.invalidateQueries({ queryKey: ["travel-visas"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر إضافة طلب التأشيرة.")),
  });

  const deleteDocMutation = useMutation({
    mutationFn: async ({ visaId, docId }: { visaId: string; docId: string }) => {
      await apiClient.delete(`/travel/visas/${visaId}/documents/${docId}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["visa-documents", expandedVisaId] }),
    onError: (err: AxiosError<{ detail?: string }>) => setErrorMsg(pickDetail(err, "تعذر حذف المستند.")),
  });

  const handleFileUpload = async (visaId: string, file: File) => {
    // Client-side validation
    if (!ALLOWED_TYPES.includes(file.type)) {
      setUploadError((prev) => ({ ...prev, [visaId]: "نوع الملف غير مدعوم. يُقبل: PDF, JPEG, PNG, GIF, DOC, DOCX" }));
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setUploadError((prev) => ({ ...prev, [visaId]: `حجم الملف يتجاوز 5 ميجابايت (${fmtSize(file.size)})` }));
      return;
    }
    setUploadError((prev) => ({ ...prev, [visaId]: "" }));
    setUploadingVisaId(visaId);

    const formData = new FormData();
    formData.append("file", file);
    try {
      await apiClient.post(`/travel/visas/${visaId}/documents`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      queryClient.invalidateQueries({ queryKey: ["visa-documents", visaId] });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || "تعذر رفع الملف.";
      setUploadError((prev) => ({ ...prev, [visaId]: msg }));
    } finally {
      setUploadingVisaId(null);
    }
  };

  const nextStatus = (current: string) => {
    const idx = STATUS_FLOW.indexOf(current);
    if (idx === -1 || idx === STATUS_FLOW.length - 1) return null;
    return STATUS_FLOW[idx + 1];
  };

  return (
    <div className="space-y-gutter">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/dashboard/travel" className="text-on-surface-variant hover:text-on-surface">
            <ArrowRight className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">متابعة التأشيرات</h1>
            <p className="font-body-md text-body-md text-on-surface-variant">كل طلبات التأشيرات عبر الحجوزات النشطة، بحالتها الحالية.</p>
          </div>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity w-fit shrink-0"
        >
          <Plus className="w-4 h-4" /> طلب تأشيرة جديد
        </button>
      </div>

      {/* ── Add Visa Modal ── */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-gutter" onClick={() => setShowAdd(false)}>
          <div className="glass-card rounded-xl w-full max-w-md p-card-padding space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="font-headline-sm text-headline-sm text-on-surface">طلب تأشيرة جديد</h2>
              <button onClick={() => setShowAdd(false)} className="text-on-surface-variant hover:text-on-surface"><X className="w-5 h-5" /></button>
            </div>
            <label className="block">
              <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">الحجز</span>
              <select className="input" value={form.case_id} onChange={(e) => setForm({ ...form, case_id: e.target.value })}>
                <option value="">اختر الحجز</option>
                {bookings?.map((b) => <option key={b.id} value={b.id}>{b.title ?? b.data?.customer_name ?? b.id}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">اسم المسافر</span>
              <input className="input" value={form.passenger_name} onChange={(e) => setForm({ ...form, passenger_name: e.target.value })} />
            </label>
            <label className="block">
              <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">رقم الجواز (اختياري)</span>
              <input className="input" value={form.passport_number} onChange={(e) => setForm({ ...form, passport_number: e.target.value })} />
            </label>
            <label className="block">
              <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">دولة الوجهة</span>
              <input className="input" value={form.destination_country} onChange={(e) => setForm({ ...form, destination_country: e.target.value })} />
            </label>
            <label className="block">
              <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">نوع التأشيرة</span>
              <select className="input" value={form.visa_type} onChange={(e) => setForm({ ...form, visa_type: e.target.value })}>
                <option value="tourist">سياحية</option>
                <option value="business">أعمال</option>
                <option value="work">عمل</option>
                <option value="transit">ترانزيت</option>
                <option value="other">أخرى</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">تكلفة الوكالة</span>
                <input type="number" dir="ltr" className="input" value={form.cost} onChange={(e) => setForm({ ...form, cost: Number(e.target.value) })} />
              </label>
              <label className="block">
                <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">الرسوم المحصّلة</span>
                <input type="number" dir="ltr" className="input" value={form.fee_charged} onChange={(e) => setForm({ ...form, fee_charged: Number(e.target.value) })} />
              </label>
            </div>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!form.case_id || !form.passenger_name || !form.destination_country || createMutation.isPending}
              className="w-full h-10 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-60 flex items-center justify-center gap-1.5"
            >
              {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null} إضافة
            </button>
          </div>
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
          `}</style>
        </div>
      )}

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setStatusFilter("")}
          className={`px-3 py-1.5 rounded-full text-body-sm font-semibold ${!statusFilter ? "bg-primary text-on-primary" : "bg-surface-container text-on-surface-variant"}`}
        >
          الكل
        </button>
        {Object.entries(STATUS_LABEL).map(([k, v]) => (
          <button
            key={k}
            onClick={() => setStatusFilter(k)}
            className={`px-3 py-1.5 rounded-full text-body-sm font-semibold ${statusFilter === k ? "bg-primary text-on-primary" : "bg-surface-container text-on-surface-variant"}`}
          >
            {v}
          </button>
        ))}
        <label className="flex items-center gap-2 text-body-sm text-on-surface-variant mr-2">
          <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
          إظهار المحذوفة
        </label>
      </div>

      {errorMsg && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error py-6">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل طلبات التأشيرات.
        </div>
      ) : !visas || visas.length === 0 ? (
        <Card><EmptyState icon={Stamp} title="لا توجد طلبات تأشيرات" description="طلبات التأشيرة بتتضاف من داخل تفاصيل كل حجز." /></Card>
      ) : (
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4 w-8" />
                  <th className="px-6 py-4">المسافر</th>
                  <th className="px-6 py-4">الحجز</th>
                  <th className="px-6 py-4">الوجهة</th>
                  <th className="px-6 py-4">النوع</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4">موعد القرار المتوقع</th>
                  <th className="px-6 py-4">الرسوم</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {visas.map((v) => {
                  const next = nextStatus(v.status);
                  const isExpanded = expandedVisaId === v.id;
                  return (
                    <>
                      <tr
                        key={v.id}
                        className={`hover:bg-surface-container-lowest transition-colors ${!v.is_active ? "opacity-50" : ""}`}
                      >
                        {/* Expand toggle */}
                        <td className="px-3 py-4">
                          <button
                            onClick={() => setExpandedVisaId(isExpanded ? null : v.id)}
                            className="text-on-surface-variant hover:text-primary"
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                        </td>
                        <td className="px-6 py-4 font-medium">
                          {v.passenger_name}
                          {!v.is_active && <span className="mr-2 text-[10px] text-error font-bold">محذوف</span>}
                          {v.passport_number && <span className="block text-[11px] text-on-surface-variant font-data-mono" dir="ltr">{v.passport_number}</span>}
                        </td>
                        <td className="px-6 py-4">
                          <Link href={`/dashboard/cases/${v.case_id}`} className="text-primary hover:underline">{v.booking_title ?? "—"}</Link>
                        </td>
                        <td className="px-6 py-4 text-on-surface-variant">{v.destination_country}</td>
                        <td className="px-6 py-4 text-on-surface-variant">{v.visa_type}</td>
                        <td className="px-6 py-4"><Badge tone={STATUS_TONE[v.status] ?? "neutral"}>{STATUS_LABEL[v.status] ?? v.status}</Badge></td>
                        <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">
                          {v.expected_decision_date ? (
                            <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {v.expected_decision_date}</span>
                          ) : "—"}
                        </td>
                        <td className="px-6 py-4 font-data-mono" dir="ltr">{egp(v.fee_charged, v.currency)}</td>
                        <td className="px-6 py-4">
                          {next && v.is_active && (
                            <button
                              onClick={() => requestTransition(v.id, next)}
                              disabled={!!transitioningId}
                              className="text-primary font-semibold text-body-sm flex items-center gap-1 hover:underline disabled:opacity-60"
                            >
                              {transitioningId === v.id ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <>{STATUS_LABEL[next]} <ChevronLeft className="w-3.5 h-3.5" /></>
                              )}
                            </button>
                          )}
                        </td>
                      </tr>

                      {/* ── Expanded Documents Row ── */}
                      {isExpanded && (
                        <tr key={`${v.id}-docs`} className="bg-surface-container-lowest">
                          <td colSpan={9} className="px-8 py-4">
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="text-body-sm font-semibold text-on-surface flex items-center gap-1.5">
                                  <Paperclip className="w-4 h-4 text-primary" /> المستندات المرفقة
                                </span>
                                {/* Upload button */}
                                <label className={`flex items-center gap-2 h-8 px-3 rounded-lg bg-primary/10 text-primary font-semibold text-body-sm hover:bg-primary/20 transition-colors cursor-pointer ${uploadingVisaId === v.id ? "opacity-60 pointer-events-none" : ""}`}>
                                  {uploadingVisaId === v.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                                  رفع مستند
                                  <input
                                    type="file"
                                    className="hidden"
                                    accept=".pdf,.jpg,.jpeg,.png,.gif,.doc,.docx"
                                    onChange={(e) => {
                                      const file = e.target.files?.[0];
                                      if (file) handleFileUpload(v.id, file);
                                      e.target.value = "";
                                    }}
                                  />
                                </label>
                              </div>

                              {uploadError[v.id] && (
                                <p className="text-[11px] text-error flex items-center gap-1">
                                  <AlertCircle className="w-3.5 h-3.5" /> {uploadError[v.id]}
                                </p>
                              )}

                              {docsLoading ? (
                                <div className="flex items-center gap-2 text-on-surface-variant text-body-sm py-2">
                                  <Loader2 className="w-4 h-4 animate-spin" /> جاري التحميل...
                                </div>
                              ) : !docsForVisa || docsForVisa.length === 0 ? (
                                <p className="text-body-sm text-on-surface-variant py-2">لا توجد مستندات مرفقة بعد.</p>
                              ) : (
                                <div className="space-y-1.5">
                                  {docsForVisa.map((doc) => (
                                    <div
                                      key={doc.id}
                                      className="flex items-center justify-between bg-surface-container rounded-lg px-3 py-2"
                                    >
                                      <div className="flex items-center gap-2 min-w-0">
                                        <Paperclip className="w-3.5 h-3.5 text-outline shrink-0" />
                                        <span className="text-body-sm font-medium truncate max-w-xs">{doc.filename}</span>
                                        <span className="text-[11px] text-outline shrink-0">{fmtSize(doc.file_size_bytes)}</span>
                                      </div>
                                      <div className="flex items-center gap-2 shrink-0">
                                        <a
                                          href={`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/api/v1/travel/visas/${v.id}/documents/${doc.id}`}
                                          download={doc.filename}
                                          className="text-primary hover:underline text-body-sm flex items-center gap-1"
                                          target="_blank"
                                          rel="noopener noreferrer"
                                        >
                                          <Download className="w-3.5 h-3.5" /> تحميل
                                        </a>
                                        <button
                                          onClick={() => deleteDocMutation.mutate({ visaId: v.id, docId: doc.id })}
                                          className="text-error hover:opacity-80 p-1 rounded"
                                          title="حذف المستند"
                                        >
                                          <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
