import {
  formatDuration,
  type EnrichmentEstimate,
} from "@/features/datasets/request-types";
import { cn } from "@/lib/utils";
import { AlertTriangle, Check } from "lucide-react";

/** ETA pill for one enrichment estimate. Amber (annotation) once measured from
 *  real runs; muted + a caution mark while it's still a seeded guess; a check once done. */
export function EstimateBadge({
  estimate,
  className,
}: {
  estimate?: EnrichmentEstimate;
  className?: string;
}) {
  if (!estimate) return null;

  if (estimate.estimateSeconds == null) {
    return (
      <span
        className={cn(
          "whitespace-nowrap text-[11px] text-muted-foreground",
          className
        )}
        title={estimate.basis}
      >
        {estimate.eligible.estimable ? "n/a" : estimate.basis}
      </span>
    );
  }

  if (estimate.progress >= 0.999) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 whitespace-nowrap text-[11px] text-muted-foreground",
          className
        )}
      >
        <Check size={11} className="text-primary" />
        Done
      </span>
    );
  }

  const rough = estimate.confidence !== "measured";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px]",
        rough
          ? "bg-muted text-muted-foreground"
          : "bg-annotation/10 text-annotation",
        className
      )}
      title={`${estimate.basis} · ${estimate.eligible.unitCount} ${estimate.eligible.unit}`}
    >
      {rough && <AlertTriangle size={10} />}
      {formatDuration(estimate.estimateSeconds)}
    </span>
  );
}
