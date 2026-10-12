/** Run plans: steps an admin queues for `cipher worker`. Mirrors `cipher.schemas.ingestion.run_plan`. */

export type RunStatus = "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed" | "stopped";

export type StepPool = "cpu" | "gpu";

/** An analytic (`textExtraction`, ...), `staging`, or a follow-up step (`entityResolution`, ...). */
export type StepType = string;

export const STAGING = "staging";
export const ENTITY_RESOLUTION = "entityResolution";

export interface PlanStepInput {
  stepType: StepType;
  parameters?: Record<string, unknown>;
}

export interface RunPlanCreate {
  datasetId: string;
  note?: string;
  steps: PlanStepInput[];
}

export interface CodeVersion {
  branch: string | null;
  sha: string | null;
  lockHash: string | null;
}

/** Where a step runs: `tail -f <log>` / `ps -g <pid>` on that host. */
export interface StepProcess {
  host: string;
  workerPid: number;
  pid: number;
  log: string;
  gpu: string | null;
}

export interface PlanRun {
  id: string;
  stepType: StepType;
  command: string;
  status: RunStatus;
  position: number;
  pool: StepPool;
  services: string[];
  dependsOn: StepType[];
  parameters: Record<string, unknown>;
  worker: string | null;
  process: StepProcess | null;
  unit: string | null;
  unitCount: number;
  progress: Record<string, unknown> | null;
  errorMessage: string | null;
  dateHeartbeat: string | null;
  dateStarted: string | null;
  dateCompleted: string | null;
  durationSeconds: number | null;
  ranOn: CodeVersion | null;
  isVersionMismatch: boolean;
}

export interface RunPlan {
  planId: string;
  datasetId: string;
  status: RunStatus;
  note: string | null;
  queuedByName: string | null;
  approvedOn: CodeVersion | null;
  dateCreated: string;
  dateApproved: string | null;
  steps: PlanRun[];
}
