import {
  formatDuration,
  type EnrichmentEstimate,
} from "@/features/datasets/request-types";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

/** ETA pill for one enrichment: the remaining time measured from prior runs on this machine
 *  (amber, annotation), a check once done, or muted text when it hasn't run here yet. */
export function EstimateBadge({
  estimate,
  className,
}: {
  estimate?: EnrichmentEstimate;
  className?: string;
}) {
  // No size to time (faces, table rows): the dependency chip already says what it waits on.
  if (!estimate || !estimate.eligible.estimable) return null;

  if (estimate.estimateSeconds == null) {
    return (
      <span
        className={cn(
          "whitespace-nowrap text-[11px] text-muted-foreground",
          className
        )}
        title={estimate.basis}
      >
        {estimate.basis}
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

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-annotation/10 px-2 py-0.5 text-[11px] text-annotation",
        className
      )}
      title={`${estimate.basis} · ${estimate.eligible.unitCount} ${estimate.eligible.unit}`}
    >
      {formatDuration(estimate.estimateSeconds)}
    </span>
  );
}
