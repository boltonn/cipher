import { formatCompactNumber } from "@/lib/utils";

/** "N skipped" breakdown by reason, for progress tooltips. */
export function SkipReasons({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons).sort(([, a], [, b]) => b - a);
  if (!entries.length) return null;
  return (
    <ul className="mt-1 space-y-0.5">
      {entries.map(([reason, count]) => (
        <li key={reason} className="flex justify-between gap-4">
          <span>{reason}</span>
          <span className="tabular-nums">{formatCompactNumber(count)}</span>
        </li>
      ))}
    </ul>
  );
}
