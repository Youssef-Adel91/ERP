"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  CreditCard,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Package,
  Receipt,
  Landmark,
  ShieldCheck,
} from "lucide-react";

// ── Types (mirrors backend app/modules/billing/api.py) ───────────────────────

type PlanTier = "ENTRY" | "PROFESSIONAL" | "ENTERPRISE";
type SubscriptionState = "TRIALING" | "ACTIVE" | "PAST_DUE" | "SUSPENDED" | "CANCELLED";
type InvoiceStatus = "DRAFT" | "OPEN" | "PAID" | "VOID" | "UNCOLLECTIBLE";

interface Plan {
  code: string;
  tier: PlanTier;
  price_monthly: string;
  entitlements: Record<string, boolean | number>;
}

interface Subscription {
  id: string;
  tenant_id: string;
  plan_code: string;
  state: SubscriptionState;
  current_period_end: string;
}

interface SubscriptionInvoice {
  id: string;
  subscription_id: string;
  amount: string;
  status: InvoiceStatus;
  due_date: string;
  created_at: string;
}

const subStateMeta: Record<SubscriptionState, string> = {
  TRIALING: "bg-primary-container/10 text-primary",
  ACTIVE: "bg-success-bg text-success",
  PAST_DUE: "bg-warning-bg text-warning",
  SUSPENDED: "bg-error-container text-on-error-container",
  CANCELLED: "bg-surface-container text-on-surface-variant",
};

const subStateLabel: Record<SubscriptionState, string> = {
  TRIALING: "فترة تجريبية",
  ACTIVE: "نشط",
  PAST_DUE: "متأخر السداد",
  SUSPENDED: "موقوف (وضع القراءة فقط)",
  CANCELLED: "ملغى",
};

const invStatusMeta: Record<InvoiceStatus, string> = {
  DRAFT: "bg-surface-container text-on-surface-variant",
  OPEN: "bg-warning-bg text-warning",
  PAID: "bg-success-bg text-success",
  VOID: "bg-surface-container text-on-surface-variant",
  UNCOLLECTIBLE: "bg-error-container text-on-error-container",
};

const invStatusLabel: Record<InvoiceStatus, string> = {
  DRAFT: "مسودة",
  OPEN: "مستحقة",
  PAID: "مدفوعة",
  VOID: "ملغاة",
  UNCOLLECTIBLE: "متعذر تحصيلها",
};

const tierLabel: Record<PlanTier, string> = {
  ENTRY: "الأساسية",
  PROFESSIONAL: "الاحترافية",
  ENTERPRISE: "المؤسسات",
};

export default function BillingPage() {
  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الاشتراك والفوترة</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          إدارة باقة اشتراكك، ومتابعة فواتير الاشتراك وحالة السداد.
        </p>
      </div>

      <SubscriptionCard />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter items-start">
        <PlansCard />
        <InvoicesCard />
      </div>
    </div>
  );
}

// ── Current subscription ──────────────────────────────────────────────────────

function SubscriptionCard() {
  const { data: subscription, isLoading, isError } = useQuery({
    queryKey: ["billing-subscription"],
    queryFn: async () => {
      const res = await apiClient.get<Subscription | null>("/billing/subscription");
      return res.data;
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <CreditCard className="w-4 h-4" />
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">الاشتراك الحالي</h2>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل بيانات الاشتراك.
        </div>
      ) : !subscription ? (
        <div className="flex flex-col items-center justify-center py-8 text-on-surface-variant gap-2">
          <ShieldCheck className="w-7 h-7 text-outline-variant" />
          <p className="text-body-sm">لا يوجد اشتراك مُفعّل بعد. اختر باقة من القائمة أدناه للبدء.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1">
            <p className="text-body-sm text-on-surface-variant">الباقة</p>
            <p className="text-body-md font-semibold font-data-mono text-on-surface" dir="ltr">{subscription.plan_code}</p>
          </div>
          <div className="space-y-1">
            <p className="text-body-sm text-on-surface-variant">الحالة</p>
            <span className={`inline-block px-2 py-1 rounded text-[11px] font-bold ${subStateMeta[subscription.state]}`}>
              {subStateLabel[subscription.state]}
            </span>
          </div>
          <div className="space-y-1">
            <p className="text-body-sm text-on-surface-variant">نهاية الفترة الحالية</p>
            <p className="text-body-md font-data-mono text-on-surface" dir="ltr">
              {new Date(subscription.current_period_end).toLocaleDateString("en-GB")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Plans catalogue ────────────────────────────────────────────────────────────

function PlansCard() {
  const queryClient = useQueryClient();
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const { data: plans, isLoading, isError } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: async () => {
      const res = await apiClient.get<Plan[]>("/billing/plans");
      return res.data;
    },
  });

  const { data: subscription } = useQuery({
    queryKey: ["billing-subscription"],
    queryFn: async () => {
      const res = await apiClient.get<Subscription | null>("/billing/subscription");
      return res.data;
    },
  });

  const subscribeMutation = useMutation({
    mutationFn: async (planCode: string) => {
      const periodEnd = new Date();
      periodEnd.setMonth(periodEnd.getMonth() + 1);
      await apiClient.post("/billing/subscription", {
        plan_code: planCode,
        current_period_end: periodEnd.toISOString(),
      });
    },
    onSuccess: () => {
      setErrorMsg("");
      setSuccessMsg("تم تحديث الاشتراك بنجاح.");
      queryClient.invalidateQueries({ queryKey: ["billing-subscription"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setSuccessMsg("");
      if (err.response?.status === 403) {
        setErrorMsg("هذا الإجراء متاح فقط لمالك الحساب أو المدير.");
      } else {
        setErrorMsg(pickDetail(err, "تعذر تحديث الاشتراك."));
      }
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <Package className="w-4 h-4" />
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">الباقات المتاحة</h2>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الباقات.
        </div>
      ) : !plans || plans.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-on-surface-variant gap-2">
          <Package className="w-7 h-7 text-outline-variant" />
          <p className="text-body-sm">لا توجد باقات مُعرَّفة بعد.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {plans.map((plan) => {
            const isCurrent = subscription?.plan_code === plan.code;
            return (
              <div
                key={plan.code}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  isCurrent ? "border-primary bg-primary-container/5" : "border-outline-variant/40"
                }`}
              >
                <div>
                  <p className="text-body-md font-semibold text-on-surface">{tierLabel[plan.tier]}</p>
                  <p className="text-body-sm text-on-surface-variant font-data-mono" dir="ltr">
                    {plan.code} · {plan.price_monthly} EGP / شهر
                  </p>
                </div>
                {isCurrent ? (
                  <span className="px-2 py-1 rounded text-[11px] font-bold bg-success-bg text-success">
                    الباقة الحالية
                  </span>
                ) : (
                  <button
                    onClick={() => subscribeMutation.mutate(plan.code)}
                    disabled={subscribeMutation.isPending}
                    className="h-9 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70"
                  >
                    {subscribeMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "اشترك"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {successMsg && (
        <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg text-body-sm font-medium border border-success">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> {successMsg}
        </div>
      )}
      {errorMsg && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
        </div>
      )}
    </div>
  );
}

// ── Subscription invoices ────────────────────────────────────────────────────

function InvoicesCard() {
  const { data: invoices, isLoading, isError } = useQuery({
    queryKey: ["billing-invoices"],
    queryFn: async () => {
      const res = await apiClient.get<SubscriptionInvoice[]>("/billing/invoices");
      return res.data;
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <Receipt className="w-4 h-4" />
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">فواتير الاشتراك</h2>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الفواتير.
        </div>
      ) : !invoices || invoices.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-on-surface-variant gap-2">
          <Landmark className="w-7 h-7 text-outline-variant" />
          <p className="text-body-sm">لا توجد فواتير اشتراك بعد.</p>
        </div>
      ) : (
        <div className="divide-y divide-outline-variant/30 max-h-96 overflow-y-auto">
          {invoices.map((inv) => (
            <div key={inv.id} className="flex items-center justify-between py-3 px-1">
              <div>
                <p className="text-body-md font-medium font-data-mono" dir="ltr">{inv.amount} EGP</p>
                <p className="text-body-sm text-outline font-data-mono" dir="ltr">
                  استحقاق {new Date(inv.due_date).toLocaleDateString("en-GB")}
                </p>
              </div>
              <span className={`px-2 py-1 rounded text-[11px] font-bold ${invStatusMeta[inv.status]}`}>
                {invStatusLabel[inv.status]}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
