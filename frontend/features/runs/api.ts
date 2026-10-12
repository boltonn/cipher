import { apiClient } from "@/lib/api-client";
import type { RunPlan, RunPlanCreate } from "./types";

export const runService = {
  listPlans: async (datasetId: string): Promise<RunPlan[]> => {
    const { data } = await apiClient.get<RunPlan[]>("/runs/plans", { params: { datasetId } });
    return data;
  },
  createPlan: async (plan: RunPlanCreate): Promise<RunPlan> => {
    const { data } = await apiClient.post<RunPlan>("/runs/plans", plan);
    return data;
  },
  cancelRun: async (runId: string): Promise<void> => {
    await apiClient.post(`/runs/${runId}/cancel`);
  },
  requeueRun: async (runId: string): Promise<void> => {
    await apiClient.post(`/runs/${runId}/requeue`);
  },
};
