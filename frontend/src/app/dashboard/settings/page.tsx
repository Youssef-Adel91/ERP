"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  Settings2,
  User as UserIcon,
  Plug,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  MessageCircle,
} from "lucide-react";

/**
 * Settings Hub — was a dead nav link (/dashboard/settings had no page).
 * Two sections: "عام" (General — read-only profile from the real
 * GET /auth/me, no fake editable fields since no profile-update endpoint
 * exists yet) and "التكاملات" (Integrations — WhatsApp Business API
 * config, the first of what should grow into a real integrations list).
 */

type Tab = "general" | "integrations";

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("general");

  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الإعدادات</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">إدارة حسابك وتكاملات النظام.</p>
      </div>

      <div className="flex gap-2 border-b border-outline-variant">
        <TabButton active={tab === "general"} onClick={() => setTab("general")} icon={UserIcon} label="عام" />
        <TabButton active={tab === "integrations"} onClick={() => setTab("integrations")} icon={Plug} label="التكاملات" />
      </div>

      {tab === "general" ? <GeneralTab /> : <IntegrationsTab />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof UserIcon;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 text-body-md font-semibold border-b-2 -mb-px transition-colors ${
        active ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
      }`}
    >
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

// ── General ────────────────────────────────────────────────────────────────────

interface MeResponse {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  role: string;
  is_active: boolean;
}

function GeneralTab() {
  const { data: me, isLoading, isError } = useQuery({
    queryKey: ["settings-me"],
    queryFn: async () => {
      const res = await apiClient.get<MeResponse>("/auth/me");
      return res.data;
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-4 max-w-xl">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
          <Settings2 className="w-4 h-4" />
        </div>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">بيانات الحساب</h2>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError || !me ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل بيانات الحساب.
        </div>
      ) : (
        <div className="space-y-3">
          <InfoRow label="الاسم الكامل" value={me.full_name} />
          <InfoRow label="البريد الإلكتروني" value={me.email} mono />
          <InfoRow label="الدور" value={me.role} />
          <InfoRow label="معرّف المستأجر (Tenant ID)" value={me.tenant_id} mono />
          <InfoRow label="حالة الحساب" value={me.is_active ? "نشط" : "غير نشط"} />
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-outline-variant/30 last:border-0">
      <span className="text-body-sm text-on-surface-variant">{label}</span>
      <span className={`text-body-sm text-on-surface ${mono ? "font-data-mono" : "font-medium"}`} dir={mono ? "ltr" : undefined}>
        {value}
      </span>
    </div>
  );
}

// ── Integrations ───────────────────────────────────────────────────────────────

function IntegrationsTab() {
  return (
    <div className="space-y-gutter">
      <WhatsAppConfigCard />
    </div>
  );
}

interface WhatsAppConfig {
  id: string;
  phone_number_id: string;
  access_token_ref: string | null;
  webhook_verify_token: string | null;
  is_active: boolean;
}

interface WhatsAppForm {
  phone_number_id: string;
  access_token_ref: string;
  webhook_verify_token: string;
  is_active: boolean;
}

function WhatsAppConfigCard() {
  const queryClient = useQueryClient();
  const [showToken, setShowToken] = useState(false);
  const [showVerify, setShowVerify] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const { data: config, isLoading } = useQuery({
    queryKey: ["whatsapp-config"],
    queryFn: async () => {
      const res = await apiClient.get<WhatsAppConfig | null>("/whatsapp/config");
      return res.data;
    },
  });

  const { register, handleSubmit, reset } = useForm<WhatsAppForm>({
    defaultValues: { phone_number_id: "", access_token_ref: "", webhook_verify_token: "", is_active: false },
  });

  useEffect(() => {
    if (config) {
      reset({
        phone_number_id: config.phone_number_id,
        access_token_ref: config.access_token_ref ?? "",
        webhook_verify_token: config.webhook_verify_token ?? "",
        is_active: config.is_active,
      });
    }
  }, [config, reset]);

  const mutation = useMutation({
    mutationFn: async (data: WhatsAppForm) => {
      await apiClient.put("/whatsapp/config", data);
    },
    onSuccess: () => {
      setErrorMsg("");
      setSuccessMsg("تم حفظ إعدادات واتساب بنجاح.");
      queryClient.invalidateQueries({ queryKey: ["whatsapp-config"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setSuccessMsg("");
      setErrorMsg(pickDetail(err, "تعذر حفظ الإعدادات."));
    },
  });

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-5 max-w-xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
            <MessageCircle className="w-4 h-4" />
          </div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">تكامل واتساب (WhatsApp Business API)</h2>
        </div>
        {config && (
          <span className={`px-2 py-1 rounded text-[11px] font-bold ${config.is_active ? "bg-success-bg text-success" : "bg-surface-container text-on-surface-variant"}`}>
            {config.is_active ? "مُفعّل" : "غير مُفعّل بعد"}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : (
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">معرّف رقم الهاتف (Phone Number ID)</label>
            <input {...register("phone_number_id")} dir="ltr" className="input-field font-mono" />
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">
              مرجع رمز الوصول (Access Token Ref)
            </label>
            <div className="relative">
              <input
                {...register("access_token_ref")}
                dir="ltr"
                type={showToken ? "text" : "password"}
                placeholder="vault://secrets/whatsapp/..."
                className="input-field font-mono pl-10"
              />
              <button
                type="button"
                onClick={() => setShowToken((s) => !s)}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-body-sm text-outline">
              مرجع فقط — التوكن الفعلي يُخزَّن في الخزنة الآمنة (Vault) ولا يُحفظ أبدًا في قاعدة البيانات كنص صريح.
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">رمز التحقق من الويب هوك (Webhook Verify Token)</label>
            <div className="relative">
              <input
                {...register("webhook_verify_token")}
                dir="ltr"
                type={showVerify ? "text" : "password"}
                className="input-field font-mono pl-10"
              />
              <button
                type="button"
                onClick={() => setShowVerify((s) => !s)}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors"
              >
                {showVerify ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <label className="flex items-center gap-2 text-body-sm font-semibold text-on-surface-variant cursor-pointer">
            <input type="checkbox" {...register("is_active")} className="w-4 h-4 accent-primary" />
            تفعيل التكامل
          </label>

          <button
            type="submit"
            disabled={mutation.isPending}
            className="flex items-center justify-center gap-2 h-11 px-6 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الإعدادات
          </button>
        </form>
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
