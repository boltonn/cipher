"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { SkipReasons } from "@/features/datasets/components/skip-reasons";
import type { EnrichmentStageProgress } from "@/features/datasets/types";
import { formatCompactNumber } from "@/lib/utils";
import { Check } from "lucide-react";

const pct = (n: number, total: number) => (total ? (n / total) * 100 : 0);

/** One bar per pass of a multi-pass analytic (event extraction: calendar, gate, LLM). */
export function EnrichmentStages({
  stages,
  onShowFailures,
}: {
  stages: EnrichmentStageProgress[];
  onShowFailures: () => void;
}) {
  return (
    <ul className="mt-1.5 space-y-2 pl-14">
      {stages.map((stage) => {
        // A filtering pass "processes" every row; the ones it filtered out don't go on to the next pass.
        const passedOn = stage.completed - stage.skipped;
        const isDone = stage.total > 0 && stage.completed + stage.failed >= stage.total;
        return (
          <li key={stage.name}>
            <p className="mb-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
              <span className="text-foreground/80">{stage.label}</span>
              {isDone ? (
                <span className="inline-flex items-center gap-1">
                  <Check size={11} className="text-primary" /> Done
                </span>
              ) : (
                <span>
                  {formatCompactNumber(stage.completed)} of {formatCompactNumber(stage.total)}
                </span>
              )}
              {stage.skipped > 0 && (
                <span>
                  · {formatCompactNumber(passedOn)} passed on ·{" "}
                  {formatCompactNumber(stage.skipped)} skipped
                </span>
              )}
              {stage.failed > 0 && (
                <button
                  type="button"
                  onClick={onShowFailures}
                  className="text-destructive underline-offset-2 hover:underline"
                >
                  · {formatCompactNumber(stage.failed)} failed
                </button>
              )}
            </p>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex h-2 w-full cursor-default items-center">
                  <div className="flex h-1 w-full overflow-hidden rounded-full bg-border">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${pct(passedOn, stage.total)}%` }}
                    />
                    <div
                      className="h-full bg-muted-foreground/40 transition-all"
                      style={{ width: `${pct(stage.skipped, stage.total)}%` }}
                    />
                    <div
                      className="h-full bg-destructive/70 transition-all"
                      style={{ width: `${pct(stage.failed, stage.total)}%` }}
                    />
                  </div>
                </div>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs">
                <p className="font-medium">{stage.label}</p>
                <p>
                  {formatCompactNumber(stage.completed)} of {formatCompactNumber(stage.total)}{" "}
                  processed{isDone ? " (finished)" : ""}
                </p>
                {stage.skipped > 0 && (
                  <>
                    <p className="mt-1">
                      {formatCompactNumber(passedOn)} passed on,{" "}
                      {formatCompactNumber(stage.skipped)} skipped:
                    </p>
                    <SkipReasons reasons={stage.skipReasons} />
                  </>
                )}
                {stage.failed > 0 && <p>{formatCompactNumber(stage.failed)} failed</p>}
              </TooltipContent>
            </Tooltip>
          </li>
        );
      })}
    </ul>
  );
}
