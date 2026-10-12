import { formatDistanceToNowStrict } from "date-fns";
import type { PlanRun, RunPlan, RunStatus } from "./types";

export const LIVE: readonly RunStatus[] = ["running", "cancelling"];
export const WAITING: readonly RunStatus[] = ["queued"];
export const FINISHED: readonly RunStatus[] = ["cancelled", "completed", "failed", "stopped"];

/** A plan step with the plan it belongs to. */
export interface PlannedStep {
  step: PlanRun;
  plan: RunPlan;
}

/**
 * The step that says most about each step type right now: a live or waiting one if any (the
 * newest), else the most recent finished one. Plans arrive newest first.
 */
export function currentStepByType(plans: RunPlan[] | undefined): Map<string, PlannedStep> {
  const current = new Map<string, PlannedStep>();
  const rank = (status: RunStatus) => (LIVE.includes(status) ? 0 : WAITING.includes(status) ? 1 : 2);
  for (const plan of plans ?? []) {
    for (const step of plan.steps) {
      const held = current.get(step.stepType);
      if (!held || rank(step.status) < rank(held.step.status)) current.set(step.stepType, { step, plan });
    }
  }
  return current;
}

export const ago = (iso: string | null | undefined) =>
  iso ? formatDistanceToNowStrict(new Date(iso), { addSuffix: true }) : "";

const since = (iso: string | null | undefined) =>
  iso ? formatDistanceToNowStrict(new Date(iso)) : "";

export const host = (worker: string | null) => worker?.split(":")[0] ?? null;

export const shortSha = (sha: string | null | undefined) => sha?.slice(0, 8) ?? "unknown";

/** What a step is doing, for the right-hand side of a pipeline row. */
export function stepStateText(step: PlanRun, labelFor: (stepType: string) => string): string {
  switch (step.status) {
    case "queued":
      return step.dependsOn.length
        ? `Queued · after ${step.dependsOn.map(labelFor).join(", ")}`
        : "Queued · waiting for a worker";
    case "running":
      return [`Running on ${host(step.worker) ?? "a worker"}`, since(step.dateStarted)].filter(Boolean).join(" · ");
    case "cancelling":
      return "Stopping…";
    case "cancelled":
      return `Cancelled ${ago(step.dateCompleted)}`;
    case "failed":
      return `Failed ${ago(step.dateCompleted)}`;
    case "stopped":
      return `Stopped ${ago(step.dateCompleted)}`;
    case "completed":
      return `Done ${ago(step.dateCompleted)}`;
  }
}

/** Tooltip text when a step ran on another commit than the one its plan was approved on. */
export function versionNote(step: PlanRun, plan: RunPlan): string | null {
  if (!step.isVersionMismatch || !step.ranOn) return null;
  const approved = plan.approvedOn;
  return `Ran on ${step.ranOn.branch ?? "?"} @ ${shortSha(step.ranOn.sha)}; approved on ${approved?.branch ?? "?"} @ ${shortSha(approved?.sha)}`;
}

/** Staging's own progress: `{found, staged, alreadyStaged, isListingDone}`. */
export function stagingProgress(step: PlanRun) {
  const progress = (step.progress ?? {}) as Record<string, unknown>;
  return {
    found: Number(progress.found ?? 0),
    staged: Number(progress.staged ?? 0),
    alreadyStaged: Number(progress.alreadyStaged ?? 0),
    isListingDone: Boolean(progress.isListingDone),
  };
}
