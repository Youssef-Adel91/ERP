import type { LucideIcon } from "lucide-react";

export type StatCardTone = "primary" | "secondary" | "tertiary" | "error";

const iconToneClasses: Record<StatCardTone, string> = {
  primary: "bg-primary-container/10 text-primary",
  secondary: "bg-secondary-container/10 text-secondary",
  tertiary: "bg-tertiary-container/10 text-tertiary",
  error: "bg-error-container/10 text-error",
};

/**
 * StatCard — the KPI card from direction_6_data_visual_dashboard:
 * icon badge top-right, label, big mono value, optional caption.
 *
 * NOTE: the Stitch mock also shows a trend badge ("+12%") on every card.
 * That's left out here deliberately — the real dashboard has no backend
 * endpoint for period-over-period comparison yet, and showing a fabricated
 * percentage on a financial dashboard would be actively misleading. Wire
 * up `trend` once `/dashboard/metrics` returns real comparison data.
 */
export function StatCard({
  icon: Icon,
  tone,
  label,
  value,
  caption,
}: {
  icon: LucideIcon;
  tone: StatCardTone;
  label: string;
  value: string;
  caption?: string;
}) {
  return (
    <div className="glass-card p-card-padding rounded-xl shadow-sm hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2 rounded-lg ${iconToneClasses[tone]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <p className="text-body-sm text-outline font-medium">{label}</p>
      <h3 className="text-headline-md font-headline-md mt-1 text-on-surface" dir="ltr">{value}</h3>
      {caption && <p className="text-[10px] text-outline-variant mt-2">{caption}</p>}
    </div>
  );
}
