"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { featureMeta } from "@/features/entities/lib/resolution-features";
import type { ResolutionFeature } from "@/features/entities/types";
import { cn } from "@/lib/utils";

/** One "why" chip on a resolution / merge candidate, with a plain-language tooltip. */
export function FeatureChip({ feature }: { feature: ResolutionFeature }) {
  const conflict = feature.level === "conflict";
  const meta = featureMeta(feature.name);
  const sign = feature.contribution > 0 ? "+" : "";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "cursor-help rounded-full border px-1.5 py-0.5 text-[11px]",
            conflict
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "border-annotation/30 bg-annotation/10 text-annotation-foreground dark:text-annotation"
          )}
        >
          {meta.label}
          {feature.contribution !== 0 && (
            <span className="ml-1 tabular-nums opacity-70">
              {sign}
              {feature.contribution.toFixed(1)}
            </span>
          )}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs flex-col items-start gap-1">
        <span className="font-medium capitalize">{meta.label}</span>
        {meta.blurb && <span className="opacity-90">{meta.blurb}</span>}
        {feature.detail && (
          <span className="opacity-70">This match: {feature.detail}</span>
        )}
        <span className="opacity-70">
          {conflict
            ? "Conflict — vetoes this match."
            : `Contributes ${sign}${feature.contribution.toFixed(
                1
              )} to the score (log-odds).`}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}
