import { apiClient } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";

/** Mirrors backend `cipher/schemas/llm.py::ModelOption`. */
export interface ChatModelOption {
  id: string;
  provider: string;
  label: string;
  /** The server can authenticate this model with its own key -- no client key needed. */
  hasKey: boolean;
}

/** Mirrors backend `cipher/schemas/llm.py::AgentConfig` (GET /chat/config). */
export interface AgentConfig {
  hasServerKey: boolean;
  models: ChatModelOption[];
  defaultModelId: string;
}

/** Which models the server already holds an API key for, so the UI only prompts when it must. */
export function useAgentConfig() {
  return useQuery({
    queryKey: ["chat", "config"],
    queryFn: async () => {
      const { data } = await apiClient.get<AgentConfig>("/chat/config", {
        suppressErrorToast: true,
      });
      return data;
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
}
