import type { ReactNode } from "react";

/**
 * Card — the "glass-card" surface used across every Stitch reference
 * (direction_6_*). Matches: `.glass-card p-card-padding rounded-xl
 * shadow-sm hover:shadow-md transition-shadow` from the design system.
 *
 * Deliberately capped at `rounded-xl` (12px) — the design system's
 * borderRadius scale tops out there (`DEFAULT`/`lg`/`xl`/`full`), so cards
 * should never reach for `rounded-2xl` even though Tailwind config makes
 * it technically available.
 */
export function Card({
  children,
  className = "",
  hoverable = true,
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
        "glass-card rounded-xl shadow-sm",
        hoverable ? "hover:shadow-md transition-shadow" : "",
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

/** Header row for a Card that contains a table/list — title + right-aligned meta (count, filter, etc). */
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
