import type { ReactNode } from "react";

export type BadgeTone = "primary" | "secondary" | "tertiary" | "error" | "success" | "warning" | "neutral";

/**
 * Badge — status pill matching the Stitch pattern used for statuses,
 * trend indicators, and counts across all 10 design references:
 * `px-2 py-0.5 rounded text-body-sm` with a `{tone}-container/20` tint
 * background and `text-{tone}` foreground.
 */
const toneClasses: Record<BadgeTone, string> = {
  primary: "bg-primary-container/20 text-primary",
  secondary: "bg-secondary-container/20 text-secondary",
  tertiary: "bg-tertiary-container/20 text-tertiary",
  error: "bg-error-container/20 text-error",
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  neutral: "bg-surface-container text-on-surface-variant",
};

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${toneClasses[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Dot-prefixed variant — used for entity statuses (posted/draft/active/inactive) per the Stitch table pattern. */
export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <Badge tone={tone}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {children}
    </Badge>
  );
}
