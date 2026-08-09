"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { CheckCircle2, Circle, Sparkles, X, ChevronDown, ChevronUp } from "lucide-react";

/**
 * First-run onboarding checklist for a newly registered tenant. Before
 * this existed, a new merchant landed on a completely empty dashboard
 * (zero revenue, zero receivables, empty tables everywhere) with no
 * indication of what to do first — a real gap for anyone who isn't
 * already familiar with ERP software.
 *
 * Steps are derived from real data (contacts/items/invoices counts, the
 * WhatsApp config endpoint) rather than a separate "onboarding_state"
 * table — so it's always accurate even if the user does things outside
 * this widget's flow, and there's nothing new to keep in sync.
 *
 * Dismissal is stored in localStorage (client-only preference, not
 * business data) so it doesn't reappear every visit once the user closes
 * it, but it auto-hides on its own once every step is complete anyway.
 */

interface Step {
  key: string;
  label: string;
  href: string;
  done: boolean;
}

const DISMISS_KEY = "nexus-erp-onboarding-dismissed";

export default function OnboardingChecklist() {
  const [dismissed, setDismissed] = useState(true); // default true until we check localStorage, to avoid a flash
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISS_KEY) === "1");
  }, []);

  const { data: contacts } = useQuery({
    queryKey: ["onboarding-contacts"],
    queryFn: async () => (await apiClient.get<{ items: unknown[] }>("/contacts", { params: { limit: 1 } })).data,
    enabled: !dismissed,
  });

  const { data: items } = useQuery({
    queryKey: ["onboarding-items"],
    queryFn: async () => (await apiClient.get<unknown[]>("/inventory/items")).data,
    enabled: !dismissed,
  });

  const { data: invoices } = useQuery({
    queryKey: ["onboarding-invoices"],
    queryFn: async () => (await apiClient.get<unknown[]>("/sales/invoices")).data,
    enabled: !dismissed,
  });

  const { data: whatsappConfig } = useQuery({
    queryKey: ["onboarding-whatsapp"],
    queryFn: async () => {
      try {
        const res = await apiClient.get("/whatsapp/config");
        return res.data;
      } catch {
        return null;
      }
    },
    enabled: !dismissed,
  });

  if (dismissed) return null;

  const steps: Step[] = [
    { key: "contact", label: "أضف أول جهة اتصال (عميل أو مورد)", href: "/dashboard/contacts", done: !!contacts && contacts.items.length > 0 },
    { key: "item", label: "أضف أول صنف في المخزون", href: "/dashboard/inventory", done: !!items && items.length > 0 },
    { key: "invoice", label: "أنشئ أول فاتورة مبيعات", href: "/dashboard/sales", done: !!invoices && invoices.length > 0 },
    { key: "whatsapp", label: "فعّل تكامل واتساب لإشعار العملاء تلقائيًا (اختياري)", href: "/dashboard/settings", done: !!whatsappConfig },
  ];

  const doneCount = steps.filter((s) => s.done).length;
  const allDone = doneCount === steps.length;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  };

  // Once every step is complete, don't keep nagging — but let the user
  // dismiss it manually before that too.
  if (allDone) return null;

  return (
    <div className="glass-card rounded-xl p-card-padding space-y-3 border border-primary/20">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center gap-2 text-right flex-1"
        >
          <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="flex-1">
            <h2 className="font-headline-sm text-headline-sm text-on-surface">ابدأ في استخدام النظام</h2>
            <p className="text-body-sm text-on-surface-variant">{doneCount} من {steps.length} خطوات مكتملة</p>
          </div>
          {collapsed ? <ChevronDown className="w-4 h-4 text-on-surface-variant" /> : <ChevronUp className="w-4 h-4 text-on-surface-variant" />}
        </button>
        <button
          onClick={dismiss}
          aria-label="إخفاء"
          className="w-8 h-8 rounded-md flex items-center justify-center text-on-surface-variant hover:text-error hover:bg-error-container transition-colors shrink-0"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="h-1.5 rounded-full bg-surface-container-high overflow-hidden">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${(doneCount / steps.length) * 100}%` }}
        />
      </div>

      {!collapsed && (
        <div className="divide-y divide-outline-variant/30">
          {steps.map((step) => (
            <Link
              key={step.key}
              href={step.href}
              className="flex items-center gap-3 py-2.5 hover:bg-surface-container-lowest transition-colors -mx-2 px-2 rounded-lg"
            >
              {step.done ? (
                <CheckCircle2 className="w-4 h-4 text-secondary shrink-0" />
              ) : (
                <Circle className="w-4 h-4 text-outline-variant shrink-0" />
              )}
              <span className={`text-body-sm ${step.done ? "text-on-surface-variant line-through" : "text-on-surface"}`}>
                {step.label}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
