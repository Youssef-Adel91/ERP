import type { ReactNode } from "react";

export type BadgeTone = "primary" | "secondary" | "tertiary" | "error" | "success" | "warning" | "info" | "neutral";

/**
 * Badge — Trust Core status pill: tinted background + matching text colour.
 * Tones map to the design system (brand / success / warning / danger / info / ai).
 */
const toneClasses: Record<BadgeTone, string> = {
  primary: "bg-primary-fixed text-primary",
  secondary: "bg-success-bg text-success",
  tertiary: "bg-tertiary-fixed text-tertiary",
  error: "bg-error-container text-error",
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
  info: "bg-info-bg text-info",
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
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12px] font-semibold ${toneClasses[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Dot-prefixed variant — used for entity statuses (posted/draft/active/inactive). */
export function StatusBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <Badge tone={tone}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {children}
    </Badge>
  );
}
