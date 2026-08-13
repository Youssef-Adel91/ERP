"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  Store,
  Loader2,
  AlertCircle,
  BedDouble,
  Car,
  Plane,
  UsersRound,
  MessageCircle,
  Puzzle,
  PackageCheck,
  Layers,
} from "lucide-react";

// ── Types (mirrors backend app/modules/system/api_plugins.py) ───────────────

interface PluginEntry {
  key: string;
  name_ar: string;
  description_ar: string;
  is_active: boolean;
  is_demo?: boolean;
  video_url?: string | null;
  package_key: string | null;
}

interface PackageEntry {
  key: string;
  name_ar: string;
  description_ar: string;
  plugin_keys: string[];
  is_active: boolean;
  is_partial: boolean;
}

const pluginIcon: Record<string, typeof Puzzle> = {
  hospitality: BedDouble,
  rental: Car,
  travel: Plane,
  recruitment: UsersRound,
  whatsapp: MessageCircle,
};

export default function MarketplacePage() {
  return (
    <div className="space-y-gutter">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">سوق الإضافات</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          ثبّت باقة قطاعية كاملة دفعة واحدة، أو فعّل إضافات فردية حسب احتياج نشاطك.
        </p>
      </div>

      <PackagesSection />
      <IndividualPluginsSection />
    </div>
  );
}

// ── Packages (bundles, installed/uninstalled as one unit) ────────────────────

function PackagesSection() {
  const queryClient = useQueryClient();
  const [errorMsg, setErrorMsg] = useState("");

  const { data: packages, isLoading, isError } = useQuery({
    queryKey: ["marketplace-packages"],
    queryFn: async () => {
      const res = await apiClient.get<PackageEntry[]>("/packages");
      return res.data;
    },
  });

  const installMutation = useMutation({
    mutationFn: async ({ key, action }: { key: string; action: "install" | "uninstall" }) => {
      await apiClient.post(`/packages/${key}/${action}`);
    },
    onSuccess: () => {
      setErrorMsg("");
      queryClient.invalidateQueries({ queryKey: ["marketplace-packages"] });
      queryClient.invalidateQueries({ queryKey: ["marketplace-plugins"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setErrorMsg(pickDetail(err, "تعذر تنفيذ العملية على الباقة."));
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Layers className="w-4 h-4 text-on-surface-variant" />
        <h2 className="font-headline-sm text-headline-sm text-on-surface">الباقات القطاعية</h2>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الباقات.
        </div>
      ) : !packages || packages.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant">لا توجد باقات متاحة حاليًا.</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter">
          {packages.map((pkg) => {
            const isPending = installMutation.isPending && installMutation.variables?.key === pkg.key;
            return (
              <div
                key={pkg.key}
                className={`glass-card rounded-xl p-card-padding space-y-4 border ${
                  pkg.is_active ? "border-primary" : "border-outline-variant/40"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-11 h-11 rounded-lg flex items-center justify-center shrink-0 ${
                        pkg.is_active ? "bg-primary-container/10 text-primary" : "bg-surface-container text-on-surface-variant"
                      }`}
                    >
                      <PackageCheck className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="font-headline-sm text-headline-sm text-on-surface">{pkg.name_ar}</h3>
                      <p className="text-body-sm text-on-surface-variant mt-0.5">{pkg.description_ar}</p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {pkg.plugin_keys.map((key) => (
                    <span key={key} className="px-2 py-0.5 rounded text-[11px] font-semibold bg-surface-container text-on-surface-variant">
                      {key}
                    </span>
                  ))}
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span
                    className={`px-2 py-1 rounded text-[11px] font-bold ${
                      pkg.is_active
                        ? "bg-success-bg text-success"
                        : pkg.is_partial
                        ? "bg-warning-bg text-warning"
                        : "bg-surface-container text-on-surface-variant"
                    }`}
                  >
                    {pkg.is_active ? "مثبَّتة بالكامل" : pkg.is_partial ? "مثبَّتة جزئيًا" : "غير مثبَّتة"}
                  </span>

                  {pkg.is_active ? (
                    <button
                      onClick={() => installMutation.mutate({ key: pkg.key, action: "uninstall" })}
                      disabled={isPending}
                      className="h-9 px-4 rounded-lg border border-error text-error font-semibold text-body-sm hover:bg-error-container transition-colors disabled:opacity-60"
                    >
                      {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : "إلغاء تثبيت الباقة"}
                    </button>
                  ) : (
                    <button
                      onClick={() => installMutation.mutate({ key: pkg.key, action: "install" })}
                      disabled={isPending}
                      className="h-9 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70"
                    >
                      {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : pkg.is_partial ? "استكمال التثبيت" : "تثبيت الباقة"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
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

// ── Individual plugins ────────────────────────────────────────────────────────

function IndividualPluginsSection() {
  const queryClient = useQueryClient();
  const [errorMsg, setErrorMsg] = useState("");

  const { data: plugins, isLoading, isError } = useQuery({
    queryKey: ["marketplace-plugins"],
    queryFn: async () => {
      const res = await apiClient.get<PluginEntry[]>("/plugins");
      return res.data;
    },
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ key, is_active }: { key: string; is_active: boolean }) => {
      await apiClient.put(`/plugins/${key}`, { is_active });
    },
    onMutate: async ({ key, is_active }) => {
      await queryClient.cancelQueries({ queryKey: ["marketplace-plugins"] });
      const previous = queryClient.getQueryData<PluginEntry[]>(["marketplace-plugins"]);
      queryClient.setQueryData<PluginEntry[]>(["marketplace-plugins"], (old) =>
        old?.map((p) => (p.key === key ? { ...p, is_active } : p))
      );
      setErrorMsg("");
      return { previous };
    },
    onError: (err: AxiosError<{ detail?: string }>, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["marketplace-plugins"], context.previous);
      }
      setErrorMsg(pickDetail(err, "تعذر تحديث الإضافة."));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["marketplace-plugins"] });
      queryClient.invalidateQueries({ queryKey: ["marketplace-packages"] });
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Store className="w-4 h-4 text-on-surface-variant" />
        <h2 className="font-headline-sm text-headline-sm text-on-surface">إضافات فردية</h2>
      </div>
      <p className="text-body-sm text-on-surface-variant -mt-2">
        يمكن تفعيل أو إلغاء أي إضافة بمفردها — حتى لو كانت ضمن باقة — طالما لا توجد إضافة أخرى فعّالة تعتمد عليها.
      </p>

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الإضافات.
        </div>
      ) : !plugins || plugins.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
          <Store className="w-7 h-7 text-outline-variant" />
          <p className="text-body-sm">لا توجد إضافات متاحة حاليًا.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-gutter">
          {plugins.map((plugin) => {
            const Icon = pluginIcon[plugin.key] ?? Puzzle;
            const isPending =
              toggleMutation.isPending && toggleMutation.variables?.key === plugin.key;
            return (
              <div
                key={plugin.key}
                className={`glass-card rounded-xl p-card-padding space-y-4 border transition-colors ${
                  plugin.is_active ? "border-primary" : "border-outline-variant/40 bg-surface-variant/10"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div
                    className={`w-11 h-11 rounded-lg flex items-center justify-center ${
                      plugin.is_active ? "bg-primary-container/10 text-primary" : "bg-surface-container text-on-surface-variant"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>
                  <button
                    role="switch"
                    aria-checked={plugin.is_active}
                    disabled={isPending}
                    onClick={() =>
                      toggleMutation.mutate({ key: plugin.key, is_active: !plugin.is_active })
                    }
                    className={`relative w-12 h-7 rounded-full transition-colors shrink-0 disabled:opacity-60 ${
                      plugin.is_active ? "bg-primary" : "bg-outline-variant/50"
                    }`}
                  >
                    <span
                      className={`absolute top-1 w-5 h-5 rounded-full bg-surface shadow-sm transition-transform ${
                        plugin.is_active ? "translate-x-[-1.5rem]" : "translate-x-[-0.25rem]"
                      } right-0`}
                    />
                  </button>
                </div>

                <div className="space-y-1">
                  <h3 className="font-headline-sm text-headline-sm text-on-surface">{plugin.name_ar}</h3>
                  <p className="text-body-sm text-on-surface-variant">{plugin.description_ar}</p>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`inline-block px-2 py-1 rounded text-[11px] font-bold ${
                      plugin.is_active ? "bg-success-bg text-success" : "bg-surface-container text-on-surface-variant"
                    }`}
                  >
                    {plugin.is_active ? "مُفعّلة" : "غير مُفعّلة"}
                  </span>
                  {plugin.package_key && (
                    <span className="inline-block px-2 py-1 rounded text-[11px] font-semibold bg-primary-container/10 text-primary">
                      جزء من باقة
                    </span>
                  )}
                </div>
              </div>
            );
          })}
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
