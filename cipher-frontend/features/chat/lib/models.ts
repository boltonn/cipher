export interface ModelOption {
  id: string;
  label: string;
  provider: string;
}

export const MODELS: ModelOption[] = [
  { id: "openai:gpt-4o-mini", label: "GPT-4o Mini", provider: "openai" },
  { id: "openai:gpt-4o", label: "GPT-4o", provider: "openai" },
  {
    id: "anthropic:claude-haiku-4-5-20251001",
    label: "Claude Haiku",
    provider: "anthropic",
  },
  {
    id: "anthropic:claude-sonnet-4-5",
    label: "Claude Sonnet",
    provider: "anthropic",
  },
  {
    id: "google:gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    provider: "google",
  },
  {
    id: "google:gemini-2.5-flash-lite",
    label: "Gemini 2.5 Flash Lite",
    provider: "google",
  },
  { id: "google:gemini-2.5-pro", label: "Gemini 2.5 Pro", provider: "google" },
  {
    id: "local:gemma-3n-E2B-it",
    label: "Gemma 3n E2B (local)",
    provider: "local",
  },
];

export const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
  local: "Local",
};

export function getModelLabel(modelId: string): string {
  return MODELS.find((m) => m.id === modelId)?.label ?? modelId;
}
