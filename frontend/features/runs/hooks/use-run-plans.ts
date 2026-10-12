import { runService } from "@/features/runs/api";
import type { RunPlan, RunPlanCreate } from "@/features/runs/types";
import { LIVE, WAITING } from "@/features/runs/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export const runKeys = {
  all: ["run-plans"] as const,
  dataset: (datasetId: string) => ["run-plans", datasetId] as const,
};

const isActive = (plans: RunPlan[] | undefined) =>
  plans?.some((plan) => plan.steps.some((step) => LIVE.includes(step.status) || WAITING.includes(step.status))) ??
  false;

/** A dataset's recent plans; polls every 5 s while a step is queued or running. */
export function useRunPlans(datasetId: string) {
  return useQuery({
    queryKey: runKeys.dataset(datasetId),
    queryFn: () => runService.listPlans(datasetId),
    refetchInterval: (query) => (isActive(query.state.data) ? 5_000 : false),
  });
}

/** Admin plan actions; each refreshes the plans and the pipeline's progress when it lands. */
export function useRunPlanActions() {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: runKeys.all });
    client.invalidateQueries({ queryKey: ["datasets"] });
  };
  return {
    create: useMutation({ mutationFn: (plan: RunPlanCreate) => runService.createPlan(plan), onSuccess: refresh }),
    cancelRun: useMutation({ mutationFn: runService.cancelRun, onSuccess: refresh }),
    requeueRun: useMutation({ mutationFn: runService.requeueRun, onSuccess: refresh }),
  };
}
