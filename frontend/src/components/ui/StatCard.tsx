import type { LucideIcon } from "lucide-react";

export type StatCardTone = "primary" | "secondary" | "tertiary" | "error";

const iconToneClasses: Record<StatCardTone, string> = {
  primary: "bg-primary-fixed text-primary",
  secondary: "bg-success-bg text-success",
  tertiary: "bg-tertiary-fixed text-tertiary",
  error: "bg-error-container text-error",
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
    <div className="glass-card p-card-padding rounded-lg">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2.5 rounded-md ${iconToneClasses[tone]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <p className="text-body-sm text-on-surface-variant font-medium">{label}</p>
      <h3 className="text-[28px] leading-10 font-bold mt-1 text-on-surface" dir="ltr">{value}</h3>
      {caption && <p className="text-body-sm text-outline mt-2">{caption}</p>}
    </div>
  );
}
