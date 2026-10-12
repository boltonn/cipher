"use client";

import { useResolutionRun } from "@/features/datasets/api";
import type { SweepStep } from "@/features/datasets/types";
import { RUN_STATUS_ICON } from "@/features/runs/components/run-status-icon";
import { stepStateText, type PlannedStep } from "@/features/runs/utils";
import { formatCompactNumber, humanize } from "@/lib/utils";
import { AlertTriangle, Check, Circle, GitMerge, Loader2 } from "lucide-react";

const STATUS_LABEL: Record<string, string> = {
  running: "Running",
  completed: "Done",
  failed: "Failed",
  stopped: "Stopped",
};

/**
 * Entity resolution as one pipeline stage: not a per-file enrichment but a dataset-wide sweep
 * (`cipher resolve-entities`), so it reports its own steps -- same names, match names, match
 * new entities, places, links -- each with a bar while it runs.
 */
export function ResolutionStage({
  datasetId,
  planned,
  menu,
}: {
  datasetId: string;
  /** Its step in a plan, when it is queued or running from the app. */
  planned?: PlannedStep;
  /** The step's `⋯` actions. */
  menu?: React.ReactNode;
}) {
  const { data: run, isPending } = useResolutionRun(datasetId);
  if (isPending) return null;
  const queued = planned?.step.status === "queued" ? planned.step : undefined;

  return (
    <div className="group/row border-t border-border/60 py-2.5">
      <div className="flex items-center gap-3 pl-7">
        <span className="flex w-4 shrink-0 justify-center">
          {queued ? (
            RUN_STATUS_ICON.queued
          ) : !run ? (
            <Circle className="size-3 text-muted-foreground/50" />
          ) : run.status === "running" ? (
            <Loader2 className="size-3.5 animate-spin text-primary" />
          ) : run.status === "completed" ? (
            <Check className="size-3.5 text-primary" />
          ) : (
            <AlertTriangle className="size-3.5 text-destructive" />
          )}
        </span>
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <GitMerge className="size-3 shrink-0 text-muted-foreground" />
          <span className="text-sm text-foreground">Entity resolution</span>
          <span className="text-[11px] text-muted-foreground">
            dataset-wide, after extraction
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
          {queued ? (
            stepStateText(queued, (stepType) => humanize(stepType))
          ) : run ? (
            <>
              {STATUS_LABEL[run.status] ?? run.status}
              {run.status !== "running" &&
                ` · ${new Date(run.dateCompleted ?? run.dateStarted).toLocaleString()}`}
              {run.durationSeconds != null &&
                ` · ${Math.round(run.durationSeconds / 60)} min`}
            </>
          ) : (
            "Not run yet"
          )}
          {menu}
        </span>
      </div>
      {run?.errorMessage && (
        <p className="mt-1 pl-14 text-[11px] text-destructive">
          {run.errorMessage}
        </p>
      )}
      {!!run?.steps.length && (
        <ul className="mt-1.5 space-y-2 pl-14">
          {run.steps.map((step) => (
            <StepBar key={step.name} step={step} />
          ))}
        </ul>
      )}
    </div>
  );
}

function StepBar({ step }: { step: SweepStep }) {
  const pct = step.total
    ? (step.done / step.total) * 100
    : step.status === "completed"
      ? 100
      : 0;
  return (
    <li>
      <p className="mb-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
        <span className="text-foreground/80">{step.label}</span>
        {step.status === "completed" ? (
          <span className="inline-flex items-center gap-1">
            <Check size={11} className="text-primary" /> Done
            {step.total > 1 && ` · ${formatCompactNumber(step.total)}`}
          </span>
        ) : step.status === "running" ? (
          <span>
            {formatCompactNumber(step.done)} of{" "}
            {formatCompactNumber(step.total)}
          </span>
        ) : (
          <span>Waiting</span>
        )}
      </p>
      <div className="flex h-1 w-full overflow-hidden rounded-full bg-border">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </li>
  );
}
