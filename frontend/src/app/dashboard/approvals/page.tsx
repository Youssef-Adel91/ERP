"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  CheckSquare,
  Check,
  X,
  Loader2,
  AlertCircle,
  Clock,
  ShieldAlert,
  FileText,
} from "lucide-react";

// ── Types (mirrors backend app/modules/approvals/api.py) ──────────────────────

type ApprovalRequestState = "pending" | "approved" | "rejected" | "withdrawn" | "escalated" | "expired";

interface ApprovalRequest {
  id: string;
  document_type: string;
  document_id: string;
  state: ApprovalRequestState;
  requested_by: string;
  due_at: string | null;
  created_at: string;
  resolution_comment: string | null;
}

const stateMeta: Record<ApprovalRequestState, { label: string; classes: string }> = {
  pending: { label: "بانتظار القرار", classes: "bg-primary-container/10 text-primary" },
  approved: { label: "معتمد", classes: "bg-success-bg text-success" },
  rejected: { label: "مرفوض", classes: "bg-error-container text-on-error-container" },
  withdrawn: { label: "مسحوب", classes: "bg-surface-container text-on-surface-variant" },
  escalated: { label: "تم التصعيد", classes: "bg-warning-bg text-warning" },
  expired: { label: "منتهي الصلاحية", classes: "bg-surface-container text-on-surface-variant" },
};

export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [globalError, setGlobalError] = useState("");
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [decidingAction, setDecidingAction] = useState<"approve" | "reject" | null>(null);

  const { data: requests, isLoading, isError } = useQuery({
    queryKey: ["approval-requests", "pending"],
    queryFn: async () => {
      const res = await apiClient.get<ApprovalRequest[]>("/approvals/requests", {
        params: { state: "pending" },
      });
      return res.data;
    },
  });

  const decideMutation = useMutation({
    mutationFn: async ({ id, decision, comment }: { id: string; decision: "approve" | "reject"; comment?: string }) => {
      await apiClient.post(`/approvals/requests/${id}/decide`, { decision, comment: comment || undefined });
    },
    onMutate: ({ id, decision }) => {
      setGlobalError("");
      setDecidingId(id);
      setDecidingAction(decision);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approval-requests"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      if (err.response?.status === 403) {
        setGlobalError("لا يمكنك اعتماد طلب قمت بإنشائه - فصل المهام (Segregation of Duties).");
      } else if (err.response?.status === 409) {
        setGlobalError(err.response.data?.detail || "هذا الطلب لم يعد بانتظار قرار (ربما تم اتخاذ قرار بشأنه بالفعل).");
      } else {
        setGlobalError(pickDetail(err, "تعذر تسجيل القرار."));
      }
    },
    onSettled: () => {
      setDecidingId(null);
      setDecidingAction(null);
    },
  });

  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الموافقات</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          جميع الطلبات المعلّقة في محرك الموافقات — الاعتماد يخضع لقاعدة فصل المهام (لا يمكن لمنشئ الطلب اعتماده).
        </p>
      </div>

      {globalError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <ShieldAlert className="w-4 h-4 shrink-0" /> {globalError}
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل طلبات الموافقة.
          </div>
        ) : !requests || requests.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <CheckSquare className="w-8 h-8 text-outline-variant" />
            <p className="text-body-md">لا توجد طلبات بانتظار الموافقة حاليًا.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">نوع المستند</th>
                  <th className="px-6 py-4">معرّف المستند</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4">تاريخ الطلب</th>
                  <th className="px-6 py-4">الموعد النهائي</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {requests.map((req) => {
                  const busy = decidingId === req.id;
                  const meta = stateMeta[req.state];
                  return (
                    <tr key={req.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4 text-outline shrink-0" />
                          <span className="font-medium">{req.document_type}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-on-surface-variant font-data-mono text-body-sm" dir="ltr">
                        {req.document_id.slice(0, 8)}…
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[11px] font-bold ${meta.classes}`}>{meta.label}</span>
                      </td>
                      <td className="px-6 py-4 text-on-surface-variant font-data-mono text-body-sm" dir="ltr">
                        {new Date(req.created_at).toLocaleDateString("en-GB")}
                      </td>
                      <td className="px-6 py-4 text-on-surface-variant font-data-mono text-body-sm" dir="ltr">
                        {req.due_at ? (
                          new Date(req.due_at).toLocaleDateString("en-GB")
                        ) : (
                          <span className="flex items-center gap-1 opacity-60"><Clock className="w-3.5 h-3.5" /> —</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2 justify-end">
                          <button
                            onClick={() => decideMutation.mutate({ id: req.id, decision: "approve" })}
                            disabled={busy}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success-bg text-success font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50"
                          >
                            {busy && decidingAction === "approve" ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Check className="w-3.5 h-3.5" />
                            )}
                            اعتماد
                          </button>
                          <button
                            onClick={() => decideMutation.mutate({ id: req.id, decision: "reject" })}
                            disabled={busy}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-error-container text-on-error-container font-semibold text-body-sm hover:opacity-80 transition-opacity disabled:opacity-50"
                          >
                            {busy && decidingAction === "reject" ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <X className="w-3.5 h-3.5" />
                            )}
                            رفض
                          </button>
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
    </div>
  );
}
