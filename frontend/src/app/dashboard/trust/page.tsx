"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient } from "@/lib/api-client";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  ShieldX,
  Loader2,
  AlertCircle,
  Search,
  PackageCheck,
  PackageX,
  PackageMinus,
} from "lucide-react";

// ── Types (mirrors backend app/modules/trust/api.py) ──────────────────────────

type RiskBand = "UNKNOWN" | "NEW" | "GOOD" | "CAUTION" | "HIGH_RISK";

interface ReputationResult {
  band: RiskBand;
  explanation: string;
  distinct_tenant_count: number;
}

const bandMeta: Record<RiskBand, { label: string; icon: React.ElementType; classes: string }> = {
  GOOD: { label: "جيد", icon: ShieldCheck, classes: "bg-success-bg text-success border-success" },
  CAUTION: { label: "تحذير", icon: ShieldAlert, classes: "bg-warning-bg text-warning border-warning" },
  HIGH_RISK: { label: "مخاطرة عالية", icon: ShieldX, classes: "bg-error-container text-on-error-container border-error" },
  NEW: { label: "جديد", icon: ShieldQuestion, classes: "bg-primary-container/10 text-primary border-primary/30" },
  UNKNOWN: { label: "غير معروف", icon: ShieldQuestion, classes: "bg-surface-container text-on-surface-variant border-outline-variant" },
};

// ── Lookup form ────────────────────────────────────────────────────────────────

const lookupSchema = z.object({
  phone: z.string().min(10, "رقم الهاتف غير صالح"),
});
type LookupForm = z.infer<typeof lookupSchema>;

// ── Contribution form ────────────────────────────────────────────────────────

const outcomeOptions = [
  { value: "DELIVERED", label: "تم التسليم", icon: PackageCheck },
  { value: "RETURNED", label: "مرتجع", icon: PackageMinus },
  { value: "REFUSED", label: "رفض الاستلام", icon: PackageX },
] as const;

const contributionSchema = z.object({
  phone: z.string().min(10, "رقم الهاتف غير صالح"),
  outcome: z.enum(["DELIVERED", "RETURNED", "REFUSED"]),
});
type ContributionForm = z.infer<typeof contributionSchema>;

export default function TrustNetworkPage() {
  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">شبكة الثقة</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          تقييم مخاطر العملاء عبر شبكة تجار مصر — بدون أي بيانات شخصية خام، فقط تصنيف آمن (K-Anonymity).
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter items-start">
        <LookupCard />
        <ContributionCard />
      </div>
    </div>
  );
}

// ── Lookup card ────────────────────────────────────────────────────────────────

function LookupCard() {
  const [result, setResult] = useState<ReputationResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const { register, handleSubmit, formState: { errors } } = useForm<LookupForm>({
    resolver: zodResolver(lookupSchema),
    defaultValues: { phone: "" },
  });

  const mutation = useMutation({
    mutationFn: async (data: LookupForm) => {
      const res = await apiClient.post<ReputationResult>("/trust/reputation/query", { phone: data.phone });
      return res.data;
    },
    onSuccess: (data) => {
      setErrorMsg("");
      setResult(data);
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setResult(null);
      if (err.response?.status === 403) {
        setErrorMsg("بوابة المعاملة بالمثل: يجب أن تساهم في شبكة الثقة خلال آخر 30 يومًا قبل الاستعلام عن أي رقم.");
      } else if (err.response?.status === 422) {
        setErrorMsg(err.response.data?.detail || "صيغة رقم الهاتف غير صحيحة.");
      } else {
        setErrorMsg(err.response?.data?.detail || "تعذر الاستعلام عن شبكة الثقة.");
      }
    },
  });

  const onSubmit = (data: LookupForm) => mutation.mutate(data);
  const meta = result ? bandMeta[result.band] : null;

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-5">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <Search className="w-4 h-4" />
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">الاستعلام عن تقييم</h2>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex items-start gap-3">
        <div className="flex-1 space-y-1.5">
          <input
            {...register("phone")}
            dir="ltr"
            placeholder="+20 10 1234 5678"
            className="input-field font-mono"
          />
          {errors.phone && <p className="text-body-sm text-error">{errors.phone.message}</p>}
        </div>
        <button
          type="submit"
          disabled={mutation.isPending}
          className="h-11 px-5 rounded-lg bg-primary text-on-primary font-bold text-body-md flex items-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-70 shrink-0"
        >
          {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          استعلام
        </button>
      </form>

      {errorMsg && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
        </div>
      )}

      {result && meta && (
        <div className={`rounded-xl border p-4 flex items-start gap-3 ${meta.classes}`}>
          <meta.icon className="w-6 h-6 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-headline-sm text-headline-sm">{meta.label}</span>
              <span className="text-body-sm opacity-80 font-data-mono" dir="ltr">({result.band})</span>
            </div>
            <p className="text-body-sm opacity-90">{result.explanation}</p>
            <p className="text-body-sm opacity-70">
              عدد التجار المساهمين: <span className="font-data-mono" dir="ltr">{result.distinct_tenant_count}</span>
            </p>
          </div>
        </div>
      )}

      {!result && !errorMsg && (
        <div className="rounded-xl border border-outline-variant border-dashed p-4 text-body-sm text-on-surface-variant text-center">
          أدخل رقم هاتف العميل لعرض تقييمه عبر الشبكة.
        </div>
      )}
    </div>
  );
}

// ── Contribution card ─────────────────────────────────────────────────────────

function ContributionCard() {
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const { register, handleSubmit, reset, formState: { errors } } = useForm<ContributionForm>({
    resolver: zodResolver(contributionSchema),
    defaultValues: { phone: "", outcome: "DELIVERED" },
  });

  const mutation = useMutation({
    mutationFn: async (data: ContributionForm) => {
      await apiClient.post("/trust/contributions", { phone: data.phone, outcome: data.outcome });
    },
    onSuccess: () => {
      setErrorMsg("");
      setSuccessMsg("تم تسجيل النتيجة في شبكة الثقة بنجاح.");
      reset();
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setSuccessMsg("");
      setErrorMsg(err.response?.data?.detail || "تعذر تسجيل المساهمة.");
    },
  });

  const onSubmit = (data: ContributionForm) => mutation.mutate(data);

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-5">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-secondary-container/20 text-secondary flex items-center justify-center">
          <PackageCheck className="w-4 h-4" />
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">الإبلاغ عن نتيجة شحنة</h2>
      </div>
      <p className="text-body-sm text-on-surface-variant -mt-3">
        كل مساهمة تُحسب برقم الهاتف مُشفّرًا فقط (HMAC-SHA256) — لا يتم تخزين أي رقم صريح.
      </p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-body-sm font-semibold text-on-surface-variant">رقم هاتف العميل</label>
          <input
            {...register("phone")}
            dir="ltr"
            placeholder="+20 10 1234 5678"
            className="input-field font-mono"
          />
          {errors.phone && <p className="text-body-sm text-error">{errors.phone.message}</p>}
        </div>

        <div className="space-y-1.5">
          <label className="text-body-sm font-semibold text-on-surface-variant">نتيجة الشحنة</label>
          <div className="grid grid-cols-3 gap-2">
            {outcomeOptions.map((opt) => (
              <label
                key={opt.value}
                className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-outline-variant cursor-pointer has-[:checked]:border-primary has-[:checked]:bg-primary-container/10 transition-colors"
              >
                <input type="radio" value={opt.value} {...register("outcome")} className="sr-only" />
                <opt.icon className="w-5 h-5 text-on-surface-variant" />
                <span className="text-body-sm text-center">{opt.label}</span>
              </label>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70"
        >
          {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} تسجيل المساهمة
        </button>
      </form>

      {successMsg && (
        <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg text-body-sm font-medium border border-success">
          <ShieldCheck className="w-4 h-4 shrink-0" /> {successMsg}
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
