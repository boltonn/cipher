import { useEffect, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ChatAutonomy } from "../types";

interface ChatStore {
  keys: Record<string, string>;
  model: string;
  /** Datasets the conversation is scoped to; empty = all the user can access. */
  datasetIds: string[];
  autonomy: ChatAutonomy;
  setKey: (provider: string, key: string) => void;
  setModel: (model: string) => void;
  setDatasetIds: (datasetIds: string[]) => void;
  setAutonomy: (autonomy: ChatAutonomy) => void;
}

// The server holds a key for this one out of the box (LLM__* env vars); other
// providers need a key added in the model settings popover.
const DEFAULT_MODEL = "google:gemini-2.5-flash";

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      keys: {},
      model: DEFAULT_MODEL,
      datasetIds: [],
      autonomy: "guided",
      setKey: (provider, key) =>
        set((s) => ({ keys: { ...s.keys, [provider]: key } })),
      setModel: (model) => set({ model }),
      setDatasetIds: (datasetIds) => set({ datasetIds }),
      setAutonomy: (autonomy) => set({ autonomy }),
    }),
    {
      name: "chat-config",
      version: 2,
      // v0 shipped a hardcoded OpenAI default that has no server key; move those
      // installs (that never explicitly picked it) onto the server-backed default.
      migrate: (persisted, version) => {
        const state = persisted as ChatStore & { datasetId?: string };
        if (version === 0 && state?.model === "openai:gpt-4o-mini") {
          state.model = DEFAULT_MODEL;
        }
        // v1 scoped chat to a single `datasetId`; v2 scopes to a list.
        if (version < 2) {
          const { datasetId, ...rest } = state;
          return { ...rest, datasetIds: datasetId ? [datasetId] : [] };
        }
        return state;
      },
    }
  )
);

// Reusable hook to safe-guard against local-storage flashes/hydration mismatches
export function useChatStoreHydrated() {
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Check if it already finished or listen to when it finishes
    const checkHydration = () =>
      setHydrated(useChatStore.persist.hasHydrated());

    checkHydration();

    const unsubFinish = useChatStore.persist.onFinishHydration(checkHydration);
    return () => unsubFinish();
  }, []);

  return hydrated;
}
