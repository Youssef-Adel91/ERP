"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { AlertTriangle, X, Loader2, ShieldAlert } from "lucide-react";

/**
 * Dashboard widget for app.modules.cases.services.alerts — surfaces
 * expiring passport/visa/document dates buried in Travel and Recruitment
 * Cases' dynamic JSON payloads. Read-only (GET /cases/alerts/expirations);
 * dismissal is client-side/session-only since there's no persisted
 * Notification model to write a "dismissed" flag to (see the backend
 * service's docstring — this was a deliberate choice, not an oversight).
 */

type Severity = "expired" | "critical" | "warning";

interface ExpirationAlert {
  case_id: string;
  case_title: string | null;
  plugin_key: string;
  case_type_code: string;
  field_path: string;
  expiry_date: string;
  days_remaining: number;
  severity: Severity;
  assigned_to: string | null;
}

const severityMeta: Record<Severity, { badge: string; label: string }> = {
  expired: { badge: "bg-error-container text-on-error-container", label: "منتهي" },
  critical: { badge: "bg-error-container text-on-error-container", label: "حرج" },
  warning: { badge: "bg-warning-bg text-warning", label: "تنبيه" },
};

export default function ExpirationAlertsWidget() {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const { data: alerts, isLoading, isError } = useQuery({
    queryKey: ["case-expiration-alerts"],
    queryFn: async () => {
      const res = await apiClient.get<ExpirationAlert[]>("/cases/alerts/expirations", {
        params: { threshold_days: 60 },
      });
      return res.data;
    },
    refetchInterval: 5 * 60_000, // poll every 5 minutes
  });

  const visibleAlerts = useMemo(
    () => (alerts ?? []).filter((a) => !dismissed.has(`${a.case_id}:${a.field_path}`)),
    [alerts, dismissed]
  );

  const dismiss = (key: string) => setDismissed((prev) => new Set(prev).add(key));

  // Nothing to show and nothing loading/erroring — don't clutter the dashboard.
  if (!isLoading && !isError && visibleAlerts.length === 0) return null;

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-3">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-warning-bg text-warning flex items-center justify-center">
          <ShieldAlert className="w-4 h-4" />
        </div>
        <div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">تنبيهات انتهاء الصلاحية</h2>
          <p className="text-body-sm text-on-surface-variant">جوازات، تأشيرات، ومستندات على وشك الانتهاء</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-6 text-on-surface-variant gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> جاري التحقق...
        </div>
      ) : isError ? (
        <p className="text-body-sm text-error">تعذر تحميل تنبيهات الصلاحية.</p>
      ) : (
        <div className="divide-y divide-outline-variant/30">
          {visibleAlerts.map((a) => {
            const key = `${a.case_id}:${a.field_path}`;
            const meta = severityMeta[a.severity];
            return (
              <div key={key} className="flex items-center gap-3 py-2.5">
                <AlertTriangle className={`w-4 h-4 shrink-0 ${a.severity === "warning" ? "text-warning" : "text-error"}`} />
                <Link href={`/dashboard/cases/${a.case_id}`} className="flex-1 min-w-0 hover:underline">
                  <p className="text-body-sm font-medium text-on-surface truncate">
                    {a.case_title ?? "بدون عنوان"} — <span className="text-on-surface-variant">{a.field_path}</span>
                  </p>
                  <p className="text-[12px] text-outline font-data-mono" dir="ltr">
                    {a.expiry_date} ·{" "}
                    {a.days_remaining < 0
                      ? `منتهي منذ ${Math.abs(a.days_remaining)} يوم`
                      : `متبقي ${a.days_remaining} يوم`}
                  </p>
                </Link>
                <span className={`px-2 py-1 rounded text-[11px] font-bold shrink-0 ${meta.badge}`}>{meta.label}</span>
                <button
                  onClick={() => dismiss(key)}
                  className="w-7 h-7 rounded-md flex items-center justify-center text-on-surface-variant hover:text-error hover:bg-error-container transition-colors shrink-0"
                  aria-label="إخفاء"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
