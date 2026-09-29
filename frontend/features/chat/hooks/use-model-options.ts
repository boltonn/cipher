import { useAgentConfig } from "../api";
import { MODELS, type ModelOption } from "../lib/models";

/**
 * The model picker's options come from the server (`GET /chat/config`), which knows
 * which local model is actually being served; the static list is only a fallback
 * until that loads. `effectiveModel` swaps a stale stored pick for the server default.
 */
export function useModelOptions() {
  const { data: agentConfig } = useAgentConfig();
  const options: ModelOption[] = agentConfig?.models ?? MODELS;
  const labelFor = (modelId: string) => options.find((m) => m.id === modelId)?.label ?? modelId;
  const effectiveModel = (modelId: string) =>
    agentConfig && !options.some((m) => m.id === modelId) ? agentConfig.defaultModelId : modelId;
  return { options, labelFor, effectiveModel };
}
