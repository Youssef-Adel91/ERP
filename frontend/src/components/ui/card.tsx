import type { ReactNode } from "react";

/**
 * Card — Trust Core surface: white (dark: navy) panel, 1px border, radius/lg,
 * soft shadow. Kept as the single card primitive used across all pages.
 */
export function Card({
  children,
  className = "",
  hoverable = false,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  hoverable?: boolean;
  padded?: boolean;
}) {
  return (
    <div
      className={[
        "glass-card rounded-lg",
        hoverable ? "hover:shadow-overlay transition-shadow" : "",
        padded ? "p-card-padding" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </div>
  );
}

/** Header row for a Card that contains a table/list — title + meta (count, filter, etc). */
export function CardHeader({
  title,
  meta,
  className = "",
}: {
  title: string;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`p-card-padding border-b border-outline-variant flex justify-between items-center ${className}`}>
      <h4 className="font-headline-sm text-headline-sm text-on-surface">{title}</h4>
      {meta}
    </div>
  );
}
