import { formatCompactNumber } from "@/lib/utils";

const sentenceCase = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** Body of a progress-bar tooltip: a title, summary lines, then why rows were skipped as a two-column table. */
export function ProgressTooltipBody({
  title,
  lines,
  skipReasons,
}: {
  title: string;
  lines: string[];
  skipReasons?: Record<string, number>;
}) {
  const reasons = Object.entries(skipReasons ?? {}).sort(([, a], [, b]) => b - a);
  return (
    <div className="flex min-w-48 flex-col gap-1 py-0.5">
      <p className="font-medium">{title}</p>
      {lines.map((line) => (
        <p key={line} className="text-background/80">
          {line}
        </p>
      ))}
      {reasons.length > 0 && (
        <div className="mt-1 border-t border-background/20 pt-1.5">
          <p className="mb-1 text-[11px] uppercase tracking-wide text-background/60">Skipped because</p>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
            {reasons.map(([reason, count]) => (
              <div key={reason} className="contents">
                <dt className="text-background/90">{sentenceCase(reason)}</dt>
                <dd className="text-right tabular-nums text-background/90">{formatCompactNumber(count)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
