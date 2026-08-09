import type { LucideIcon } from "lucide-react";

/** EmptyState — the "no data yet" pattern repeated across every list/table page. */
export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
      <div className="w-14 h-14 rounded-full bg-surface-container flex items-center justify-center mb-2">
        <Icon className="w-6 h-6 text-outline" />
      </div>
      <p className="text-body-md text-on-surface font-medium">{title}</p>
      {description && <p className="text-body-sm">{description}</p>}
    </div>
  );
}
