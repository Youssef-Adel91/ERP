"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAppStore } from "@/store/use-app-store";
import { RevenueTrendChart } from "@/components/dashboard/RevenueTrendChart";
import { ExpenseBreakdownChart } from "@/components/dashboard/ExpenseBreakdownChart";
import { RevenueVarianceCard } from "@/components/dashboard/RevenueVarianceCard";
import { TopCustomersCard } from "@/components/dashboard/TopCustomersCard";
import { OverdueInvoicesCard } from "@/components/dashboard/OverdueInvoicesCard";
import { AIChatWidget } from "@/components/dashboard/AIChatWidget";

/**
 * /dashboard/insights — Phase B of the AI roadmap ("داشبوردز موسّعة").
 *
 * Every widget on this page is a thin wrapper over
 * app.modules.reporting.service's typed functions — the SAME functions
 * REPORT_REGISTRY exposes to the AI Bot for function-calling (Level 1 +
 * Level 2, already live-verified over the in-app /ai/ask endpoint and
 * over WhatsApp). Nothing here is a new number or a new query; this page
 * exists so a merchant can see those real numbers as charts/cards
 * without having to phrase a question first, and can still ask the same
 * Copilot a free-form question right next to them (AIChatWidget) for
 * anything a fixed widget doesn't cover.
 */
export default function InsightsPage() {
  const { user } = useAppStore();
  const router = useRouter();

  useEffect(() => {
    if (!user) {
      router.push("/login");
    }
  }, [user, router]);

  if (!user) return null;

  return (
    <div className="space-y-gutter" dir="rtl">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">رؤى الذكاء الاصطناعي</h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          نفس الأرقام الحقيقية اللي بيجاوب بيها المساعد الذكي على واتساب — هنا في لوحة واحدة، وممكن كمان تسأله مباشرة.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
        <div className="lg:col-span-2 space-y-gutter">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter">
            <RevenueTrendChart months={6} />
            <ExpenseBreakdownChart />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-gutter">
            <RevenueVarianceCard />
            <TopCustomersCard />
          </div>
          <OverdueInvoicesCard />
        </div>

        <div className="lg:col-span-1">
          <div className="sticky top-4">
            <AIChatWidget />
          </div>
        </div>
      </div>
    </div>
  );
}
