"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useForm,
  useFieldArray,
  useWatch,
  Controller,
  type Control,
  type UseFormRegister,
  type UseFormSetValue,
} from "react-hook-form";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  ArrowRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
  History,
  Users,
  ArrowLeftRight,
  Landmark,
  Plus,
  Trash2,
  FileDown,
  Sparkles,
} from "lucide-react";

/**
 * Generic Case detail page — drives Travel, Hospitality, Rental, and
 * Recruitment all from the same screen, since all four are the same
 * underlying Case Engine (app.modules.cases) configured differently per
 * plugin via CaseType.stages[].schema (JSON Schema). This page renders a
 * form dynamically from the CURRENT stage's schema rather than hardcoding
 * per-vertical fields.
 *
 * Array-of-object fields (passenger manifests, service line items) render
 * as real add/remove row tables via react-hook-form's useFieldArray —
 * the same pattern used for the Sales ad-hoc invoice line items — instead
 * of a raw JSON textarea, since real users (Amira, Karim) shouldn't have
 * to hand-write JSON. Array-of-string fields (e.g. missing document
 * checklists) get a lighter add/remove single-input list. Anything else
 * (plain nested objects) still falls back to a JSON textarea — narrow
 * enough in practice that it isn't worth a dedicated editor yet.
 */

interface JsonSchemaProperty {
  type?: string;
  format?: string;
  enum?: string[];
  description?: string;
  default?: unknown;
  items?: {
    type?: string;
    properties?: Record<string, JsonSchemaProperty>;
    required?: string[];
  };
}
interface StageSchema {
  type: string;
  required?: string[];
  properties?: Record<string, JsonSchemaProperty>;
}
interface Stage {
  id: string;
  label: string;
  label_ar?: string;
  order: number;
  is_terminal?: boolean;
  schema?: StageSchema;
}
interface CaseType {
  id: string;
  code: string;
  name: string;
  name_ar: string | null;
  plugin_key: string;
  initial_stage: string;
  stages: Stage[];
}
interface CaseContact {
  id: string;
  contact_id: string;
  role: string;
}
interface CaseHistoryEntry {
  id: string;
  from_stage: string | null;
  to_stage: string;
  changed_at: string;
  reason: string | null;
}
interface CaseDetail {
  id: string;
  case_type_id: string;
  title: string | null;
  current_stage: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  data: Record<string, unknown>;
  contacts?: CaseContact[];
  history?: CaseHistoryEntry[];
}
interface TravelFinancials {
  total_buy_price?: number;
  total_sell_price?: number;
  total_margin?: number;
  margin_pct?: number;
  commission_amount?: number;
  currency?: string;
}

// Field-name heuristic for values that must stay dir="ltr" font-mono even
// though they're plain "string" type in the JSON Schema (passport numbers,
// prices, references) — the schema alone doesn't distinguish these from
// free-text Arabic fields like "full_name".
const TECHNICAL_FIELD_RE = /number|price|amount|passport|code|ref|iban|phone|currency/i;
const isTechnicalField = (key: string) => TECHNICAL_FIELD_RE.test(key);
const labelize = (key: string) => key.replace(/_/g, " ");

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const caseId = params.id;
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [targetStage, setTargetStage] = useState("");

  const { data: caseData, isLoading: caseLoading, isError: caseError } = useQuery({
    queryKey: ["case-detail", caseId],
    queryFn: async () => {
      const res = await apiClient.get<CaseDetail>(`/cases/${caseId}`);
      return res.data;
    },
  });

  const { data: caseTypes } = useQuery({
    queryKey: ["case-types-all"],
    queryFn: async () => {
      const res = await apiClient.get<CaseType[]>("/case-types");
      return res.data;
    },
  });

  const caseType = useMemo(
    () => caseTypes?.find((t) => t.id === caseData?.case_type_id),
    [caseTypes, caseData]
  );
  const currentStage = useMemo(
    () => caseType?.stages.find((s) => s.id === caseData?.current_stage),
    [caseType, caseData]
  );
  const nextStages = useMemo(
    () => (caseType?.stages ?? []).filter((s) => s.id !== caseData?.current_stage),
    [caseType, caseData]
  );
  const targetSchema = caseType?.stages.find((s) => s.id === targetStage)?.schema;

  const isTravel = caseType?.plugin_key === "travel";

  const { data: financials } = useQuery({
    queryKey: ["case-travel-financials", caseId],
    queryFn: async () => {
      const res = await apiClient.get<TravelFinancials>(`/travel/bookings/${caseId}/financials`);
      return res.data;
    },
    enabled: !!isTravel,
  });

  const [itineraryError, setItineraryError] = useState("");
  const itineraryMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.get(`/cases/${caseId}/itinerary.pdf`, { responseType: "blob" });
      return res.data as Blob;
    },
    onSuccess: (blob) => {
      setItineraryError("");
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `itinerary-${caseId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setItineraryError(pickDetail(err, "تعذر تحميل البرنامج السياحي."));
    },
  });

  const { register, control, handleSubmit, reset, setValue } = useForm<Record<string, any>>({ defaultValues: {} });

  useEffect(() => {
    if (!targetSchema?.properties) {
      reset({});
      return;
    }
    const defaults: Record<string, any> = {};
    for (const [key, prop] of Object.entries(targetSchema.properties)) {
      defaults[key] = prop.type === "array" ? [] : "";
    }
    reset(defaults);
  }, [targetStage, targetSchema, reset]);

  const transitionMutation = useMutation({
    mutationFn: async (values: Record<string, any>) => {
      const dataPatch: Record<string, unknown> = {};
      for (const [key, prop] of Object.entries(targetSchema?.properties ?? {})) {
        const raw = values[key];
        if (prop.type === "array") {
          if (!Array.isArray(raw) || raw.length === 0) continue;
          if (prop.items?.type === "object" && prop.items.properties) {
            dataPatch[key] = raw.map((row: Record<string, unknown>) =>
              convertRow(row, prop.items!.properties!)
            );
          } else {
            const cleaned = raw.map((v: any) => (typeof v === "object" ? v.value : v)).filter((v: string) => v !== "" && v != null);
            if (cleaned.length > 0) dataPatch[key] = cleaned;
          }
          continue;
        }
        if (raw === undefined || raw === "") continue;
        if (prop.type === "number" || prop.type === "integer") {
          dataPatch[key] = Number(raw);
        } else if (prop.type === "boolean") {
          dataPatch[key] = raw === "true";
        } else if (prop.type === "object") {
          try {
            dataPatch[key] = JSON.parse(raw);
          } catch {
            throw new Error(`الحقل "${key}" يجب أن يكون JSON صالح.`);
          }
        } else {
          dataPatch[key] = raw;
        }
      }
      await apiClient.post(`/cases/${caseId}/transition`, {
        to_stage: targetStage,
        data_patch: dataPatch,
      });
    },
    onSuccess: () => {
      setError("");
      setSuccess("تم نقل الحالة للمرحلة الجديدة بنجاح.");
      setTargetStage("");
      reset({});
      queryClient.invalidateQueries({ queryKey: ["case-detail", caseId] });
    },
    onError: (err: AxiosError<{ detail?: string }> | Error) => {
      setSuccess("");
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(pickDetail(axiosErr, err.message || "تعذر نقل الحالة."));
    },
  });

  if (caseLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-on-surface-variant gap-2">
        <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
      </div>
    );
  }
  if (caseError || !caseData) {
    return (
      <div className="flex items-center gap-2 text-body-sm text-error">
        <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل بيانات الحالة.
      </div>
    );
  }

  return (
    <div className="space-y-gutter">
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push("/dashboard/cases")}
          className="w-9 h-9 rounded-lg bg-surface-container flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors"
        >
          <ArrowRight className="w-4 h-4" />
        </button>
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface">{caseData.title ?? "بدون عنوان"}</h1>
          <p className="text-body-sm text-on-surface-variant">
            {caseType?.name_ar ?? caseType?.name} ·{" "}
            <span className="font-data-mono" dir="ltr">{caseData.id}</span>
          </p>
        </div>
        <div className="mr-auto flex items-center gap-2">
          {isTravel && (
            <button
              onClick={() => itineraryMutation.mutate()}
              disabled={itineraryMutation.isPending}
              className="flex items-center gap-2 h-9 px-3 rounded-lg border border-tertiary text-tertiary font-semibold text-body-sm hover:bg-tertiary-container/10 transition-colors disabled:opacity-60"
            >
              {itineraryMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <FileDown className="w-4 h-4" />
              )}
              تحميل البرنامج السياحي
            </button>
          )}
          <span className="px-3 py-1.5 rounded-lg text-body-sm font-bold bg-primary-container/10 text-primary">
            {currentStage?.label_ar ?? currentStage?.label ?? caseData.current_stage}
          </span>
        </div>
      </div>

      {itineraryError && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {itineraryError}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg text-body-sm font-medium border border-success">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> {success}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter items-start">
        {/* Transition panel */}
        <form
          onSubmit={handleSubmit((values) => transitionMutation.mutate(values))}
          className="lg:col-span-2 glass-card rounded-xl p-card-padding space-y-4"
        >
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
              <ArrowLeftRight className="w-4 h-4" />
            </div>
            <h2 className="font-headline-sm text-headline-sm text-on-surface">نقل إلى مرحلة جديدة</h2>
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">المرحلة التالية</label>
            <select
              value={targetStage}
              onChange={(e) => setTargetStage(e.target.value)}
              className="input-field"
            >
              <option value="">اختر مرحلة...</option>
              {nextStages.map((s) => (
                <option key={s.id} value={s.id}>{s.label_ar ?? s.label}</option>
              ))}
            </select>
          </div>

          {targetSchema?.properties && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-outline-variant/30">
              {Object.entries(targetSchema.properties).map(([key, prop]) => {
                const required = targetSchema.required?.includes(key);
                if (prop.type === "array" && prop.items?.type === "object" && prop.items.properties) {
                  return (
                    <ObjectArrayField
                      key={key}
                      fieldKey={key}
                      prop={prop}
                      required={required}
                      control={control}
                      register={register}
                      setValue={setValue}
                    />
                  );
                }
                if (prop.type === "array") {
                  return (
                    <StringArrayField key={key} fieldKey={key} required={required} control={control} />
                  );
                }
                return (
                  <RegisteredField
                    key={key}
                    fieldKey={key}
                    prop={prop}
                    required={required}
                    register={register}
                  />
                );
              })}
            </div>
          )}

          <button
            type="submit"
            disabled={!targetStage || transitionMutation.isPending}
            className="flex items-center justify-center gap-2 h-11 px-6 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {transitionMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} تنفيذ النقل
          </button>

          {/* Current data snapshot */}
          <div className="pt-3 border-t border-outline-variant/30">
            <h3 className="text-body-sm font-semibold text-on-surface-variant mb-2">البيانات الحالية للحالة</h3>
            <pre className="text-[12px] font-data-mono bg-surface-container-low rounded-lg p-3 overflow-x-auto" dir="ltr">
              {JSON.stringify(caseData.data, null, 2)}
            </pre>
          </div>
        </form>

        {/* Side panels */}
        <div className="space-y-gutter">
          {isTravel && financials && (
            <div className="glass-card rounded-xl p-card-padding space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
                  <Landmark className="w-4 h-4" />
                </div>
                <h2 className="font-headline-sm text-headline-sm text-on-surface">الملخص المالي</h2>
              </div>
              <FinancialRow label="سعر الشراء" value={financials.total_buy_price} currency={financials.currency} />
              <FinancialRow label="سعر البيع" value={financials.total_sell_price} currency={financials.currency} />
              <FinancialRow label="الهامش" value={financials.total_margin} currency={financials.currency} highlight />
              <FinancialRow label="العمولة" value={financials.commission_amount} currency={financials.currency} />
            </div>
          )}

          <div className="glass-card rounded-xl p-card-padding space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface">الأطراف المرتبطة</h2>
            </div>
            {!caseData.contacts || caseData.contacts.length === 0 ? (
              <p className="text-body-sm text-on-surface-variant">لا يوجد أطراف مرتبطة بعد.</p>
            ) : (
              <div className="space-y-2">
                {caseData.contacts.map((c) => (
                  <div key={c.id} className="flex items-center justify-between text-body-sm">
                    <span className="font-data-mono text-outline" dir="ltr">{c.contact_id.slice(0, 8)}...</span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-surface-container text-on-surface-variant">{c.role}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="glass-card rounded-xl p-card-padding space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
                <History className="w-4 h-4" />
              </div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface">سجل المراحل</h2>
            </div>
            {!caseData.history || caseData.history.length === 0 ? (
              <p className="text-body-sm text-on-surface-variant">لا يوجد سجل بعد.</p>
            ) : (
              <div className="space-y-3">
                {caseData.history.map((h) => (
                  <div key={h.id} className="text-body-sm border-r-2 border-primary pr-3">
                    <p className="font-medium text-on-surface">
                      {h.from_stage ? `${h.from_stage} → ${h.to_stage}` : `فتح على ${h.to_stage}`}
                    </p>
                    <p className="text-outline font-data-mono text-[11px]" dir="ltr">
                      {new Date(h.changed_at).toLocaleString("en-GB")}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Converts one row's values per the item schema's declared types (used for
// array-of-object fields like passenger_manifest / services on submit).
function convertRow(row: Record<string, unknown>, itemProps: Record<string, JsonSchemaProperty>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [subKey, subProp] of Object.entries(itemProps)) {
    const raw = row[subKey];
    if (raw === undefined || raw === "") continue;
    if (subProp.type === "number" || subProp.type === "integer") {
      out[subKey] = Number(raw);
    } else if (subProp.type === "boolean") {
      out[subKey] = raw === "true";
    } else {
      out[subKey] = raw;
    }
  }
  return out;
}

function emptyRow(itemProps: Record<string, JsonSchemaProperty>): Record<string, string> {
  const row: Record<string, string> = {};
  for (const key of Object.keys(itemProps)) row[key] = "";
  return row;
}

// ── Array-of-object field: real add/remove row table (passenger manifests, services) ──

function ObjectArrayField({
  fieldKey,
  prop,
  required,
  control,
  register,
  setValue,
}: {
  fieldKey: string;
  prop: JsonSchemaProperty;
  required?: boolean;
  control: Control<Record<string, any>>;
  register: UseFormRegister<Record<string, any>>;
  setValue: UseFormSetValue<Record<string, any>>;
}) {
  const { fields, append, remove } = useFieldArray({ control, name: fieldKey });
  const itemProps = prop.items?.properties ?? {};
  // Detected by shape, not by hardcoding the field name "services" — any
  // row schema carrying both service_type + buy_price gets the vendor
  // rate-card lookup, so this keeps working if a future vertical reuses
  // the same shape under a different array field name.
  const hasRateLookup = "service_type" in itemProps && "buy_price" in itemProps;

  return (
    <div className="space-y-2 sm:col-span-2">
      <div className="flex items-center justify-between">
        <label className="text-body-sm font-semibold text-on-surface-variant">
          {labelize(fieldKey)} {required && <span className="text-error">*</span>}
        </label>
        <button
          type="button"
          onClick={() => append(emptyRow(itemProps))}
          className="flex items-center gap-1 text-primary text-body-sm font-semibold hover:underline"
        >
          <Plus className="w-3.5 h-3.5" /> إضافة صف
        </button>
      </div>

      {fields.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant bg-surface-variant/10 rounded-lg p-3 text-center">
          لا توجد عناصر بعد. اضغط "إضافة صف" للبدء.
        </p>
      ) : (
        <div className="space-y-2">
          {fields.map((field, index) => (
            <div key={field.id} className="bg-surface-variant/10 border border-outline-variant/30 rounded-lg p-3 space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {Object.entries(itemProps).map(([subKey, subProp]) => (
                  <RowField
                    key={subKey}
                    name={`${fieldKey}.${index}.${subKey}`}
                    subKey={subKey}
                    subProp={subProp}
                    register={register}
                  />
                ))}
              </div>

              {hasRateLookup && (
                <RateLookupPanel
                  rowPath={`${fieldKey}.${index}`}
                  itemProps={itemProps}
                  control={control}
                  setValue={setValue}
                />
              )}

              <button
                type="button"
                onClick={() => remove(index)}
                className="flex items-center gap-1.5 text-error text-body-sm font-semibold hover:underline"
              >
                <Trash2 className="w-3.5 h-3.5" /> حذف الصف
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Vendor rate-card lookup — "magic" auto-fill for buy_price on a service row ──

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

interface VendorRateOut {
  id: string;
  vendor_id: string;
  vendor_name: string;
  service_type: string;
  description: string | null;
  buy_price: string;
  currency: string;
  valid_from: string;
  valid_until: string | null;
  cancellation_policy: string | null;
}

function RateLookupPanel({
  rowPath,
  itemProps,
  control,
  setValue,
}: {
  rowPath: string;
  itemProps: Record<string, JsonSchemaProperty>;
  control: Control<Record<string, any>>;
  setValue: UseFormSetValue<Record<string, any>>;
}) {
  const serviceType: string = useWatch({ control, name: `${rowPath}.service_type` }) ?? "";
  const debouncedServiceType = useDebouncedValue(serviceType.trim(), 400);

  const { data: rates, isFetching } = useQuery({
    queryKey: ["vendor-rate-lookup", debouncedServiceType],
    queryFn: async () => {
      const res = await apiClient.get<VendorRateOut[]>("/cases/vendors/rates", {
        params: { service_type: debouncedServiceType },
      });
      return res.data;
    },
    enabled: debouncedServiceType.length > 1,
  });

  if (!debouncedServiceType || debouncedServiceType.length <= 1) return null;

  const applyRate = (rate: VendorRateOut) => {
    setValue(`${rowPath}.buy_price`, rate.buy_price, { shouldDirty: true });
    if ("supplier_name" in itemProps) setValue(`${rowPath}.supplier_name`, rate.vendor_name, { shouldDirty: true });
    if ("supplier_id" in itemProps) setValue(`${rowPath}.supplier_id`, rate.vendor_id, { shouldDirty: true });
    if ("currency" in itemProps) setValue(`${rowPath}.currency`, rate.currency, { shouldDirty: true });
  };

  return (
    <div className="rounded-lg border border-primary/30 bg-primary-container/5 p-2 space-y-1.5">
      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-primary">
        <Sparkles className="w-3.5 h-3.5" /> أسعار الموردين المتاحة لـ "{debouncedServiceType}"
      </div>
      {isFetching ? (
        <div className="flex items-center gap-2 text-body-sm text-on-surface-variant py-1">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> جاري البحث...
        </div>
      ) : !rates || rates.length === 0 ? (
        <p className="text-[12px] text-on-surface-variant">لا توجد أسعار موردين مسجّلة لهذا النوع.</p>
      ) : (
        <div className="space-y-1">
          {rates.map((rate) => (
            <button
              key={rate.id}
              type="button"
              onClick={() => applyRate(rate)}
              className="w-full flex items-center justify-between px-2 py-1.5 rounded-md bg-surface-container-lowest hover:bg-primary-container/10 transition-colors text-right"
            >
              <span className="text-body-sm font-medium text-on-surface truncate">{rate.vendor_name}</span>
              <span className="font-data-mono text-body-sm text-primary font-bold shrink-0" dir="ltr">
                {rate.buy_price} {rate.currency}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RowField({
  name,
  subKey,
  subProp,
  register,
}: {
  name: string;
  subKey: string;
  subProp: JsonSchemaProperty;
  register: UseFormRegister<Record<string, any>>;
}) {
  const label = labelize(subKey);

  if (subProp.enum) {
    return (
      <div className="space-y-1">
        <label className="text-[12px] font-semibold text-on-surface-variant">{label}</label>
        <select {...register(name)} className="input-field h-9 text-body-sm">
          <option value="">—</option>
          {subProp.enum.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      </div>
    );
  }

  const technical = isTechnicalField(subKey);
  const inputType =
    subProp.format === "date" ? "date" : subProp.format === "date-time" ? "datetime-local" :
    subProp.type === "number" || subProp.type === "integer" ? "number" : "text";
  const ltr = inputType !== "text" || technical;

  return (
    <div className="space-y-1">
      <label className="text-[12px] font-semibold text-on-surface-variant">{label}</label>
      <input
        type={inputType}
        {...register(name)}
        dir={ltr ? "ltr" : undefined}
        className={`input-field h-9 text-body-sm ${ltr ? "font-mono" : ""}`}
      />
    </div>
  );
}

// ── Array-of-string field: lightweight add/remove single-input list ───────────

function StringArrayField({
  fieldKey,
  required,
  control,
}: {
  fieldKey: string;
  required?: boolean;
  control: Control<Record<string, any>>;
}) {
  return (
    <Controller
      name={fieldKey}
      control={control}
      render={({ field }) => {
        const values: string[] = Array.isArray(field.value) ? field.value : [];
        return (
          <div className="space-y-2 sm:col-span-2">
            <div className="flex items-center justify-between">
              <label className="text-body-sm font-semibold text-on-surface-variant">
                {labelize(fieldKey)} {required && <span className="text-error">*</span>}
              </label>
              <button
                type="button"
                onClick={() => field.onChange([...values, ""])}
                className="flex items-center gap-1 text-primary text-body-sm font-semibold hover:underline"
              >
                <Plus className="w-3.5 h-3.5" /> إضافة
              </button>
            </div>
            {values.length === 0 ? (
              <p className="text-body-sm text-on-surface-variant bg-surface-variant/10 rounded-lg p-3 text-center">
                لا توجد عناصر بعد.
              </p>
            ) : (
              <div className="space-y-2">
                {values.map((v, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      value={v}
                      onChange={(e) => {
                        const next = [...values];
                        next[i] = e.target.value;
                        field.onChange(next);
                      }}
                      dir="ltr"
                      className="input-field h-9 text-body-sm font-mono flex-1"
                    />
                    <button
                      type="button"
                      onClick={() => field.onChange(values.filter((_, idx) => idx !== i))}
                      className="w-9 h-9 rounded-lg flex items-center justify-center text-error hover:bg-error-container transition-colors shrink-0"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      }}
    />
  );
}

// ── Plain scalar field (registered directly with react-hook-form) ─────────────

function RegisteredField({
  fieldKey,
  prop,
  required,
  register,
}: {
  fieldKey: string;
  prop: JsonSchemaProperty;
  required?: boolean;
  register: UseFormRegister<Record<string, any>>;
}) {
  const label = labelize(fieldKey);

  if (prop.enum) {
    return (
      <div className="space-y-1.5">
        <label className="text-body-sm font-semibold text-on-surface-variant">
          {label} {required && <span className="text-error">*</span>}
        </label>
        <select {...register(fieldKey)} className="input-field">
          <option value="">—</option>
          {prop.enum.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      </div>
    );
  }

  if (prop.type === "boolean") {
    return (
      <div className="space-y-1.5">
        <label className="text-body-sm font-semibold text-on-surface-variant">{label}</label>
        <select {...register(fieldKey)} className="input-field">
          <option value="">—</option>
          <option value="true">نعم</option>
          <option value="false">لا</option>
        </select>
      </div>
    );
  }

  if (prop.type === "object") {
    return (
      <div className="space-y-1.5 sm:col-span-2">
        <label className="text-body-sm font-semibold text-on-surface-variant">
          {label} {required && <span className="text-error">*</span>} <span className="text-outline">(JSON)</span>
        </label>
        <textarea
          {...register(fieldKey)}
          dir="ltr"
          rows={3}
          className="input-field font-mono text-body-sm"
          placeholder="{}"
        />
      </div>
    );
  }

  const technical = isTechnicalField(fieldKey);
  const inputType =
    prop.format === "date" ? "date" : prop.format === "date-time" ? "datetime-local" :
    prop.type === "number" || prop.type === "integer" ? "number" : "text";
  const ltr = inputType !== "text" || technical;

  return (
    <div className="space-y-1.5">
      <label className="text-body-sm font-semibold text-on-surface-variant">
        {label} {required && <span className="text-error">*</span>}
      </label>
      <input
        type={inputType}
        {...register(fieldKey)}
        dir={ltr ? "ltr" : undefined}
        className={`input-field ${ltr ? "font-mono" : ""}`}
      />
    </div>
  );
}

function FinancialRow({
  label,
  value,
  currency,
  highlight,
}: {
  label: string;
  value: number | undefined;
  currency?: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-body-sm">
      <span className="text-on-surface-variant">{label}</span>
      <span className={`font-data-mono ${highlight ? "text-primary font-bold" : "text-on-surface"}`} dir="ltr">
        {value !== undefined ? `${value} ${currency ?? "EGP"}` : "—"}
      </span>
    </div>
  );
}
