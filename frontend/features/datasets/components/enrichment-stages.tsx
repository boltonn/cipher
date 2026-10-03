"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { EnrichmentStageProgress } from "@/features/datasets/types";
import { formatCompactNumber } from "@/lib/utils";

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
    <ul className="mt-1.5 space-y-1.5 pl-14">
      {stages.map((stage) => {
        // A gate "completes" every row it scores; what it filtered out is shown as skipped.
        const done = stage.completed - stage.skipped;
        return (
          <li key={stage.name}>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex h-2 w-full cursor-default items-center">
                  <div className="flex h-1 w-full overflow-hidden rounded-full bg-border">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{ width: `${pct(done, stage.total)}%` }}
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
              <TooltipContent className="text-xs">
                <p className="font-medium">{stage.label}</p>
                <p>
                  {formatCompactNumber(stage.completed)} of{" "}
                  {formatCompactNumber(stage.total)} processed
                </p>
                {stage.skipped > 0 && (
                  <p>
                    {formatCompactNumber(stage.skipped)} filtered out (not passed on to the next
                    pass)
                  </p>
                )}
                {stage.failed > 0 && <p>{formatCompactNumber(stage.failed)} failed</p>}
              </TooltipContent>
            </Tooltip>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
              <span className="text-foreground/80">{stage.label}</span>
              <span>
                {formatCompactNumber(stage.completed)} /{" "}
                {formatCompactNumber(stage.total)}
              </span>
              {stage.skipped > 0 && (
                <span>· {formatCompactNumber(stage.skipped)} filtered out</span>
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
          </li>
        );
      })}
    </ul>
  );
}
